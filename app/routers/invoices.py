"""
Invoice API.

Handles:

    GET  /api/invoices
    GET  /api/invoices/{invoice_id}
    POST /api/invoices
    POST /api/invoices/{invoice_id}/resend

Offline synchronization is handled separately by:

    POST /api/sync/invoices

Important invoice rules:

1. Product prices are final customer-facing prices.
2. Product prices already include GST.
3. GST is extracted from the inclusive amount.
4. GST is NEVER added again to the product subtotal.
5. Discount is deducted from the customer-facing subtotal.
6. grand_total is calculated by the backend and persisted.
7. gst_enabled controls whether GST is applied.
8. client_uuid provides offline idempotency.
"""

from __future__ import annotations

import json
import logging

from datetime import datetime
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_agent

from app.models import (
    Agent,
    Invoice,
)

from app.schemas import (
    InvoiceCreate,
    InvoiceItemCreate,
    InvoiceListItem,
    InvoiceOut,
    PaymentMode,
)

from app.services import storage

from app.services.invoice_service import (
    create_and_deliver,
    deliver_invoice,
)


logger = logging.getLogger(
    __name__
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/invoices",
    tags=["invoices"],
)


# ============================================================
# CONSTANTS
# ============================================================

ALLOWED_PHOTO_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
}

MONEY_QUANT = Decimal(
    "0.01"
)


# ============================================================
# MONEY HELPER
# ============================================================


def _money(
    value: Decimal | None,
) -> Decimal:
    """
    Normalize monetary values to two decimal places.
    """

    if value is None:
        value = Decimal(
            "0.00"
        )

    return Decimal(
        value
    ).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# ITEMS PARSER
# ============================================================


def _parse_items(
    raw_items: str,
) -> list[InvoiceItemCreate]:
    """
    Parse invoice items from JSON.

    Frontend sends:

        items = JSON.stringify(invoice.items)
    """

    if not raw_items:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Invoice items are required."
            ),
        )

    try:

        parsed = json.loads(
            raw_items
        )

    except json.JSONDecodeError as exc:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Invalid invoice items JSON."
            ),
        ) from exc

    if not isinstance(
        parsed,
        list,
    ):

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Invoice items must be an array."
            ),
        )

    if not parsed:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "At least one invoice item is required."
            ),
        )

    validated_items: list[
        InvoiceItemCreate
    ] = []

    for index, item in enumerate(
        parsed
    ):

        if not isinstance(
            item,
            dict,
        ):

            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_ENTITY
                ),
                detail=(
                    f"Invoice item "
                    f"{index + 1} must be an object."
                ),
            )

        try:

            validated_item = (
                InvoiceItemCreate.model_validate(
                    item
                )
            )

        except Exception as exc:

            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_ENTITY
                ),
                detail=(
                    f"Invalid invoice item "
                    f"{index + 1}: {exc}"
                ),
            ) from exc

        validated_items.append(
            validated_item
        )

    return validated_items


# ============================================================
# CAPTURED AT
# ============================================================


def _parse_captured_at(
    value: str | None,
) -> datetime:
    """
    Convert frontend ISO timestamp to datetime.
    """

    if not value:

        return datetime.now()

    value = value.strip()

    if not value:

        return datetime.now()

    try:

        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+05:30",
            )
        )

    except ValueError:

        return datetime.now()


# ============================================================
# PAYMENT MODE
# ============================================================


def _normalize_payment_mode(
    value: str | None,
) -> PaymentMode:
    """
    Normalize payment mode.

    Allowed:

        online
        cash
    """

    normalized = (
        value or "online"
    ).strip().lower()

    if normalized not in {
        "online",
        "cash",
    }:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Payment mode must be "
                "'online' or 'cash'."
            ),
        )

    return PaymentMode(
        normalized
    )


# ============================================================
# DECIMAL PARSER
# ============================================================


def _parse_decimal(
    value: str | None,
    field_name: str,
) -> Decimal:
    """
    Convert FormData value to Decimal.
    """

    if value is None:

        value = "0"

    value = str(
        value
    ).strip()

    if not value:

        value = "0"

    try:

        decimal_value = Decimal(
            value
        )

    except (
        InvalidOperation,
        ValueError,
    ) as exc:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                f"Invalid {field_name}."
            ),
        ) from exc

    if not decimal_value.is_finite():

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                f"Invalid {field_name}."
            ),
        )

    return _money(
        decimal_value
    )


# ============================================================
# GST ENABLED PARSER
# ============================================================


def _parse_bool(
    value: str | None,
    default: bool = False,
) -> bool:
    """
    Convert FormData boolean values.

    Supported:

        true
        false
        1
        0
        yes
        no
        on
        off
    """

    if value is None:

        return default

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    if normalized in {
        "true",
        "1",
        "yes",
        "on",
    }:

        return True

    if normalized in {
        "false",
        "0",
        "no",
        "off",
    }:

        return False

    raise HTTPException(
        status_code=(
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        detail=(
            "gst_enabled must be true or false."
        ),
    )


# ============================================================
# INVOICE OUTPUT
# ============================================================


def _invoice_to_output(
    invoice: Invoice,
) -> InvoiceOut:
    """
    Convert SQLAlchemy Invoice to InvoiceOut.
    """

    return InvoiceOut.model_validate(
        invoice
    )


# ============================================================
# GET INVOICE LIST
# ============================================================


@router.get(
    "",
    response_model=list[InvoiceListItem],
)
def get_invoices(
    q: str | None = None,
    db: Session = Depends(
        get_db
    ),
    agent: Agent = Depends(
        get_current_agent
    ),
) -> list[InvoiceListItem]:

    query = (
        db.query(Invoice)
        .filter(
            Invoice.agent_id
            == agent.id
        )
    )

    if q:

        search = q.strip()

        if search:

            pattern = (
                f"%{search}%"
            )

            query = query.filter(
                (
                    Invoice.customer_name.ilike(
                        pattern
                    )
                )
                |
                (
                    Invoice.invoice_number.ilike(
                        pattern
                    )
                )
                |
                (
                    Invoice.customer_phone.ilike(
                        pattern
                    )
                )
            )

    invoices = (
        query
        .order_by(
            Invoice.created_at.desc()
        )
        .all()
    )

    return [
        InvoiceListItem.model_validate(
            invoice
        )
        for invoice in invoices
    ]


# ============================================================
# GET SINGLE INVOICE
# ============================================================


@router.get(
    "/{invoice_id}",
    response_model=InvoiceOut,
)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(
        get_db
    ),
    agent: Agent = Depends(
        get_current_agent
    ),
) -> InvoiceOut:

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.agent_id == agent.id,
        )
        .first()
    )

    if not invoice:

        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Invoice not found.",
        )

    return _invoice_to_output(
        invoice
    )


# ============================================================
# CREATE INVOICE
# ============================================================


@router.post(
    "",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    client_uuid: str = Form(...),
    customer_name: str = Form(...),
    customer_phone: str | None = Form(None),
    customer_email: str | None = Form(None),
    items: str = Form(...),
    product_description: str | None = Form(None),

    # GST
    tax_percent: str = Form("0"),
    gst_enabled: str = Form("false"),

    # Discount
    discount_amount: str = Form("0"),

    # Frontend may send grand_total.
    #
    # IMPORTANT:
    # Backend does NOT trust this value.
    # It recalculates grand_total.
    grand_total: str | None = Form(None),

    payment_mode: str = Form("online"),
    notes: str | None = Form(None),
    exhibition_name: str | None = Form(None),
    captured_at: str | None = Form(None),

    photo: UploadFile = File(...),

    db: Session = Depends(
        get_db
    ),

    agent: Agent = Depends(
        get_current_agent
    ),
) -> InvoiceOut:

    """
    Create a new invoice.

    GST-inclusive pricing rules:

        Product prices already include GST.

        subtotal =
            sum(product prices)

        taxable value =
            subtotal / (1 + GST / 100)

        GST =
            subtotal - taxable value

        grand_total =
            subtotal - discount

    GST is never added again.
    """

    # ========================================================
    # BASIC VALIDATION
    # ========================================================

    client_uuid = (
        client_uuid.strip()
    )

    if not client_uuid:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "client_uuid is required."
            ),
        )

    if len(client_uuid) > 36:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "client_uuid must not exceed 36 characters."
            ),
        )

    customer_name = (
        customer_name.strip()
    )

    if not customer_name:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Customer name is required."
            ),
        )

    # ========================================================
    # IDEMPOTENCY
    # ========================================================

    existing = (
        db.query(Invoice)
        .filter(
            Invoice.client_uuid
            == client_uuid,
            Invoice.agent_id
            == agent.id,
        )
        .first()
    )

    if existing:

        return _invoice_to_output(
            existing
        )

    # ========================================================
    # ITEMS
    # ========================================================

    invoice_items = _parse_items(
        items
    )

    # ========================================================
    # PAYMENT
    # ========================================================

    normalized_payment_mode = (
        _normalize_payment_mode(
            payment_mode
        )
    )

    # ========================================================
    # GST ENABLED
    # ========================================================

    gst_is_enabled = _parse_bool(
        gst_enabled,
        default=False,
    )

    # ========================================================
    # GST RATE
    # ========================================================

    tax_value = _parse_decimal(
        tax_percent,
        "GST percentage",
    )

    if (
        tax_value < Decimal("0.00")
        or tax_value > Decimal("100.00")
    ):

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "GST percentage must be "
                "between 0 and 100."
            ),
        )

    # --------------------------------------------------------
    # If GST is disabled, force rate to zero.
    # --------------------------------------------------------

    if not gst_is_enabled:

        tax_value = Decimal(
            "0.00"
        )

    # ========================================================
    # DISCOUNT
    # ========================================================

    discount_value = _parse_decimal(
        discount_amount,
        "discount amount",
    )

    if discount_value < Decimal(
        "0.00"
    ):

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Discount amount cannot be negative."
            ),
        )

    # ========================================================
    # CALCULATE SUBTOTAL
    # ========================================================

    subtotal = _money(
        sum(
            (
                _money(
                    item.unit_price
                )
                for item in invoice_items
            ),
            Decimal("0.00"),
        )
    )

    # ========================================================
    # DISCOUNT VALIDATION
    # ========================================================

    if discount_value > subtotal:

        discount_value = subtotal

    # ========================================================
    # CALCULATE GRAND TOTAL
    # ========================================================

    grand_total_value = max(
        Decimal("0.00"),
        _money(
            subtotal
            - discount_value
        ),
    )

    # ========================================================
    # CALCULATE GST
    # ========================================================

    if (
        gst_is_enabled
        and tax_value > Decimal("0.00")
        and grand_total_value > Decimal("0.00")
    ):

        # ----------------------------------------------------
        # GST is inclusive.
        #
        # GST must be calculated from the amount actually
        # charged after discount.
        # ----------------------------------------------------

        divisor = (
            Decimal("1.00")
            + (
                tax_value
                / Decimal("100.00")
            )
        )

        taxable_value = _money(
            grand_total_value
            / divisor
        )

        gst_amount = _money(
            grand_total_value
            - taxable_value
        )

    else:

        taxable_value = grand_total_value

        gst_amount = Decimal(
            "0.00"
        )

    # ========================================================
    # PHOTO VALIDATION
    # ========================================================

    if not photo:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Product photo is required."
            ),
        )

    if not photo.content_type:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Product photo content type is missing."
            ),
        )

    if (
        photo.content_type
        not in ALLOWED_PHOTO_CONTENT_TYPES
    ):

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Unsupported product photo type."
            ),
        )

    # ========================================================
    # BUILD INVOICE DATA
    # ========================================================

    try:

        invoice_data = InvoiceCreate(
            client_uuid=client_uuid,

            customer_name=customer_name,

            customer_phone=(
                customer_phone.strip()
                if customer_phone
                else None
            ),

            customer_email=(
                customer_email.strip()
                if customer_email
                else None
            ),

            items=invoice_items,

            product_description=(
                product_description.strip()
                if product_description
                else None
            ),

            tax_percent=tax_value,

            gst_enabled=gst_is_enabled,

            discount_amount=discount_value,

            # Backend-calculated value.
            grand_total=grand_total_value,

            payment_mode=(
                normalized_payment_mode
            ),

            notes=(
                notes.strip()
                if notes
                else None
            ),

            exhibition_name=(
                exhibition_name.strip()
                if exhibition_name
                else None
            ),

            captured_at=(
                _parse_captured_at(
                    captured_at
                )
            ),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(exc),
        ) from exc

    # ========================================================
    # SAVE PHOTO
    # ========================================================

    photo_relative_path: str | None = None

    try:

        photo_relative_path = (
            await storage.save_upload(
                photo,
                "photos",
            )
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(exc),
        ) from exc

    except Exception as exc:

        logger.exception(
            "Failed to save invoice product photo."
        )

        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Unable to save product photo."
            ),
        ) from exc

    # ========================================================
    # CREATE + DELIVER
    # ========================================================

    try:

        invoice = create_and_deliver(
            db=db,

            agent=agent,

            data=invoice_data.model_dump(
                mode="json"
            ),

            photo_relative_path=(
                photo_relative_path
            ),
        )

    except ValueError as exc:

        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(exc),
        ) from exc

    except IntegrityError as exc:

        db.rollback()

        # ----------------------------------------------------
        # Race-condition-safe idempotency.
        # ----------------------------------------------------

        existing = (
            db.query(Invoice)
            .filter(
                Invoice.client_uuid
                == client_uuid,

                Invoice.agent_id
                == agent.id,
            )
            .first()
        )

        if existing:

            return _invoice_to_output(
                existing
            )

        logger.exception(
            "Database integrity error "
            "while creating invoice."
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Database error while creating invoice."
            ),
        ) from exc

    except Exception as exc:

        db.rollback()

        logger.exception(
            "Failed to create invoice."
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Invoice creation failed."
            ),
        ) from exc

    # ========================================================
    # FINAL DATABASE REFRESH
    # ========================================================

    db.refresh(
        invoice
    )

    return _invoice_to_output(
        invoice
    )


# ============================================================
# RESEND INVOICE
# ============================================================


@router.post(
    "/{invoice_id}/resend",
    response_model=InvoiceOut,
)
def resend_invoice(
    invoice_id: int,

    db: Session = Depends(
        get_db
    ),

    agent: Agent = Depends(
        get_current_agent
    ),
) -> InvoiceOut:

    """
    Resend an existing invoice.

    Delivery workflow:

        existing PDF
             |
             v
        WhatsApp
             |
             +-- failed --> SMS fallback
    """

    # ========================================================
    # FIND INVOICE
    # ========================================================

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.agent_id == agent.id,
        )
        .first()
    )

    if not invoice:

        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Invoice not found.",
        )

    # ========================================================
    # RESEND
    # ========================================================

    try:

        deliver_invoice(
            db=db,
            invoice=invoice,
        )

    except ValueError as exc:

        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(exc),
        ) from exc

    except Exception as exc:

        db.rollback()

        logger.exception(
            "Failed to resend invoice %s",
            invoice.invoice_number,
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Unable to resend invoice."
            ),
        ) from exc

    db.refresh(
        invoice
    )

    return _invoice_to_output(
        invoice
    )