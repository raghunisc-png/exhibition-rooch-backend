"""
Core invoice workflow.

Pricing rules:
- Every invoice item has its own entered selling price.
- Prices are never read from a product catalog.
- The entered item price is the final customer-facing price.
- GST is inclusive of the entered price.
- Payment mode is Online or Cash.
- Product photo is required.
- PDF generation happens after invoice creation.
- WhatsApp/SMS delivery is intentionally disabled for now.

Workflow:

    Create Invoice
        ↓
    Calculate totals
        ↓
    Save Invoice
        ↓
    Generate PDF
        ↓
    DONE

Messaging is NOT part of the current workflow.
"""

from __future__ import annotations

import logging

from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    Invoice,
    InvoiceItem,
    PaymentMode,
)

from app.services import pdf as pdf_service

from app.services.numbering import (
    generate_invoice_number,
)


logger = logging.getLogger(
    "invoice_service"
)


ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")


# ============================================================
# HELPERS
# ============================================================


def _decimal(
    value: object,
) -> Decimal:
    """
    Safely convert a value to Decimal.

    Decimal(str(value)) is used instead of
    Decimal(float) to avoid binary floating-point
    precision problems.
    """

    if value is None:
        return ZERO

    if isinstance(
        value,
        Decimal,
    ):
        return value

    try:
        return Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:

        raise ValueError(
            f"Invalid decimal value: {value}"
        ) from exc


def _money(
    value: object,
) -> Decimal:
    """
    Normalize a monetary value to two decimal places.
    """

    return _decimal(
        value
    ).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


def _normalize_payment_mode(
    value: object,
) -> PaymentMode:
    """
    Normalize payment mode to the canonical PaymentMode enum.

    Accepts strings, PaymentMode instances, and legacy enum-like
    values such as ``PaymentMode.online``.
    """

    if value is None:
        return PaymentMode.online

    if isinstance(value, PaymentMode):
        return PaymentMode(value.value)

    if hasattr(value, "value"):
        value = getattr(value, "value")

    normalized = str(value).strip().lower()

    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]

    try:
        return PaymentMode(normalized)
    except ValueError as exc:
        raise ValueError(
            "Payment mode must be either 'online' or 'cash'."
        ) from exc


# ============================================================
# CREATE INVOICE
# ============================================================


def create_invoice_row(
    db: Session,
    agent: Agent,
    data: dict,
    photo_relative_path: str | None,
) -> Invoice:
    """
    Create Invoice + InvoiceItem rows.

    Expected item structure:

        {
            "product_name": "Rings",
            "item_number": 1,
            "unit_price": 1180
        }

    The price is entered directly by the booth agent.

    Product prices are final customer-facing prices
    and already include GST.

    This function commits the database transaction.

    PDF generation happens separately.
    Messaging is intentionally disabled.
    """

    # ========================================================
    # PRODUCT PHOTO
    # ========================================================

    if not photo_relative_path:

        raise ValueError(
            "Product photo is required."
        )

    # ========================================================
    # COPY DATA
    # ========================================================

    invoice_data = dict(
        data
    )

    # ========================================================
    # EXTRACT ITEMS
    # ========================================================

    items_data = invoice_data.pop(
        "items",
        None,
    )

    if not isinstance(
        items_data,
        list,
    ):

        raise ValueError(
            "Invoice items must be a list."
        )

    if not items_data:

        raise ValueError(
            "At least one invoice item is required."
        )

    # ========================================================
    # PAYMENT MODE
    # ========================================================

    payment_mode = (
        _normalize_payment_mode(
            invoice_data.get(
                "payment_mode"
            )
        )
    )

    invoice_data[
        "payment_mode"
    ] = payment_mode

    # ========================================================
    # GST
    # ========================================================

    tax_percent = _money(
        invoice_data.get(
            "tax_percent",
            ZERO,
        )
    )

    if tax_percent < ZERO:

        raise ValueError(
            "GST percentage cannot be negative."
        )

    if tax_percent > Decimal(
        "100.00"
    ):

        raise ValueError(
            "GST percentage cannot exceed 100%."
        )

    invoice_data[
        "tax_percent"
    ] = tax_percent

    # ========================================================
    # DISCOUNT
    # ========================================================

    discount_amount = _money(
        invoice_data.get(
            "discount_amount",
            ZERO,
        )
    )

    if discount_amount < ZERO:

        raise ValueError(
            "Discount cannot be negative."
        )

    invoice_data[
        "discount_amount"
    ] = discount_amount

    # ========================================================
    # CLIENT UUID
    # ========================================================

    client_uuid = str(
        invoice_data.get(
            "client_uuid",
            "",
        )
    ).strip()

    if not client_uuid:

        raise ValueError(
            "client_uuid is required."
        )

    if len(client_uuid) > 36:

        raise ValueError(
            "client_uuid cannot exceed 36 characters."
        )

    invoice_data[
        "client_uuid"
    ] = client_uuid

    # ========================================================
    # CUSTOMER NAME
    # ========================================================

    customer_name = str(
        invoice_data.get(
            "customer_name",
            "",
        )
    ).strip()

    if not customer_name:

        raise ValueError(
            "Customer name is required."
        )

    if len(customer_name) > 150:

        raise ValueError(
            "Customer name cannot exceed 150 characters."
        )

    invoice_data[
        "customer_name"
    ] = customer_name

    # ========================================================
    # NORMALIZE OPTIONAL STRINGS
    # ========================================================

    optional_string_fields = [
        "customer_phone",
        "customer_email",
        "product_description",
        "notes",
        "exhibition_name",
    ]

    for field_name in optional_string_fields:

        value = invoice_data.get(
            field_name
        )

        if value is None:
            continue

        if isinstance(
            value,
            str,
        ):

            value = value.strip()

            invoice_data[
                field_name
            ] = value or None

    # ========================================================
    # FRONTEND-ONLY FIELDS
    # ========================================================

    invoice_data.pop(
        "photo_relative_path",
        None,
    )

    invoice_data.pop(
        "photo_base64",
        None,
    )

    invoice_data.pop(
        "photo_content_type",
        None,
    )

    # ========================================================
    # CREATE INVOICE
    # ========================================================

    try:

        invoice = Invoice(
            agent_id=agent.id,

            invoice_number=(
                generate_invoice_number(
                    db
                )
            ),

            product_photo_path=(
                photo_relative_path
            ),

            **invoice_data,
        )

        db.add(
            invoice
        )

        # ----------------------------------------------------
        # Flush so invoice.id exists.
        # ----------------------------------------------------

        db.flush()

        # ====================================================
        # CREATE INVOICE ITEMS
        # ====================================================

        subtotal = ZERO

        for item_data in items_data:

            # ------------------------------------------------
            # Basic validation
            # ------------------------------------------------

            if not isinstance(
                item_data,
                dict,
            ):

                raise ValueError(
                    "Each invoice item must be an object."
                )

            # ------------------------------------------------
            # Product name (optional)
            # ------------------------------------------------

            product_name_raw = item_data.get(
                "product_name"
            )

            product_name = (
                str(product_name_raw).strip()
                if product_name_raw is not None
                else None
            ) or None

            if (
                product_name
                and len(product_name) > 200
            ):

                raise ValueError(
                    "Product name cannot exceed "
                    "200 characters."
                )

            # ------------------------------------------------
            # Item number
            # ------------------------------------------------

            try:

                item_number = int(
                    item_data.get(
                        "item_number"
                    )
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    "Invalid item number."
                ) from exc

            if not 1 <= item_number <= 5:

                raise ValueError(
                    "Item number must be between "
                    "1 and 5."
                )

            # ------------------------------------------------
            # Price
            # ------------------------------------------------

            if (
                "unit_price"
                not in item_data
            ):

                raise ValueError(
                    f"Price is required for "
                    f"{product_name or 'item'} #{item_number}."
                )

            unit_price = _money(
                item_data[
                    "unit_price"
                ]
            )

            if unit_price < ZERO:

                raise ValueError(
                    "Product price cannot be negative."
                )

            # ------------------------------------------------
            # Create item
            # ------------------------------------------------

            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                product_name=product_name,
                item_number=item_number,
                unit_price=unit_price,
            )

            db.add(
                invoice_item
            )

            subtotal += unit_price

        # ====================================================
        # SUBTOTAL
        # ====================================================

        subtotal = _money(
            subtotal
        )

        # ====================================================
        # DISCOUNT VALIDATION
        # ====================================================

        if discount_amount > subtotal:

            raise ValueError(
                "Discount cannot exceed "
                "the invoice subtotal."
            )

        # ====================================================
        # GRAND TOTAL
        # ====================================================

        """
        Product prices already include GST.

        Example:

            Ring = ₹1,180
            GST = 18%

        ₹1,180 is already the customer-facing amount.

        Therefore:

            subtotal = ₹1,180

        GST is extracted only for reporting/PDF.

        GST must NEVER be added again.

        With discount:

            grand_total =
                subtotal - discount
        """

        grand_total = max(
            ZERO,
            _money(
                subtotal
                - discount_amount
            ),
        )

        # ----------------------------------------------------
        # Persist final authoritative total.
        # ----------------------------------------------------

        invoice.grand_total = (
            grand_total
        )

        logger.info(
            "Invoice %s calculated: "
            "subtotal=%s, discount=%s, "
            "gst_enabled=%s, gst_rate=%s, "
            "grand_total=%s",
            invoice.invoice_number,
            subtotal,
            discount_amount,
            getattr(
                invoice,
                "gst_enabled",
                False,
            ),
            tax_percent,
            grand_total,
        )

        # ====================================================
        # COMMIT
        # ====================================================

        db.commit()

        db.refresh(
            invoice
        )

        return invoice

    except (
        ValueError,
        IntegrityError,
    ):

        db.rollback()

        raise

    except Exception:

        db.rollback()

        logger.exception(
            "Unexpected error while creating invoice."
        )

        raise


# ============================================================
# GST
# ============================================================


def get_gst_breakup(
    invoice: Invoice,
) -> dict:
    """
    Return GST breakup.

    GST is inclusive in the customer-facing prices.

    If GST is disabled, all GST amounts are zero.
    """

    if not getattr(
        invoice,
        "gst_enabled",
        False,
    ):

        return {
            "gst_rate": ZERO,

            "taxable_value": _money(
                invoice.grand_total
            ),

            "gst_amount": ZERO,

            "cgst_rate": ZERO,
            "cgst_amount": ZERO,

            "sgst_rate": ZERO,
            "sgst_amount": ZERO,

            "inclusive": True,
        }

    return {
        "gst_rate": _money(
            invoice.tax_percent
        ),

        "taxable_value": (
            invoice.taxable_value
        ),

        "gst_amount": (
            invoice.tax_amount
        ),

        "cgst_rate": (
            invoice.cgst_rate
        ),

        "cgst_amount": (
            invoice.cgst_amount
        ),

        "sgst_rate": (
            invoice.sgst_rate
        ),

        "sgst_amount": (
            invoice.sgst_amount
        ),

        "inclusive": True,
    }


# ============================================================
# PDF
# ============================================================


def render_pdf(
    db: Session,
    invoice: Invoice,
) -> None:
    """
    Generate and store the invoice PDF.

    PDF generation failure is allowed to propagate
    to the caller.
    """

    relative_path = (
        pdf_service
        .generate_and_store_invoice_pdf(
            invoice
        )
    )

    if not relative_path:

        raise ValueError(
            "Invoice PDF could not be generated."
        )

    invoice.pdf_path = (
        relative_path
    )

    db.commit()

    db.refresh(
        invoice
    )


# ============================================================
# DELIVERY
# ============================================================


def deliver_invoice(
    db: Session,
    invoice: Invoice,
) -> None:
    """
    PDF-only delivery workflow.

    WhatsApp and SMS are intentionally disabled.

    Current behavior:

        1. Check whether PDF exists.
        2. Generate PDF if missing.
        3. Finish.

    No messaging provider is called.
    """

    if not invoice.pdf_path:

        render_pdf(
            db=db,
            invoice=invoice,
        )

    logger.info(
        "Invoice %s PDF is ready: %s",
        invoice.invoice_number,
        invoice.pdf_path,
    )


# ============================================================
# COMPLETE WORKFLOW
# ============================================================


def create_and_deliver(
    db: Session,
    agent: Agent,
    data: dict,
    photo_relative_path: str | None,
) -> Invoice:
    """
    Complete invoice workflow.

    Step 1:
        Create invoice and items.

    Step 2:
        Commit invoice to database.

    Step 3:
        Generate PDF.

    Step 4:
        Finish.

    WhatsApp/SMS are intentionally disabled.

    Important:

    Invoice creation is independent from PDF generation.

    If PDF generation fails, the invoice remains saved
    in the database.
    """

    # ========================================================
    # CREATE DATABASE RECORD
    # ========================================================

    invoice = create_invoice_row(
        db=db,
        agent=agent,
        data=data,
        photo_relative_path=(
            photo_relative_path
        ),
    )

    # ========================================================
    # PDF
    # ========================================================

    try:

        render_pdf(
            db=db,
            invoice=invoice,
        )

    except Exception:

        logger.exception(
            "PDF generation failed "
            "for invoice %s",
            invoice.invoice_number,
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Invoice was already committed.
        # Do not delete the invoice.
        # ----------------------------------------------------

        try:

            db.rollback()

        except Exception:

            logger.exception(
                "Database rollback failed "
                "after PDF generation error."
            )

    # ========================================================
    # FINAL REFRESH
    # ========================================================

    try:

        db.refresh(
            invoice
        )

    except Exception:

        db.rollback()

        logger.exception(
            "Could not refresh invoice %s",
            invoice.invoice_number,
        )

    return invoice