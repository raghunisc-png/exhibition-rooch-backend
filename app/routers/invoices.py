"""
Invoice API.

Online invoices are submitted as multipart/form-data because the
product photo is uploaded together with the invoice information.

The invoice contains multiple individually priced items.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_agent
from app.models import Agent, Invoice, InvoiceItem
from app.schemas import (
    InvoiceCreate,
    InvoiceListItem,
    InvoiceOut,
    ResendRequest,
)
from app.services import storage
from app.services.invoice_service import (
    create_and_deliver,
    deliver_invoice,
)

router = APIRouter(
    prefix="/api/invoices",
    tags=["invoices"],
)


MAX_PHOTO_BYTES = 8 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
}


# ============================================================
# CREATE
# ============================================================


@router.post(
    "",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    client_uuid: str = Form(...),

    customer_name: str = Form(...),

    # Optional according to the new frontend.
    customer_phone: str | None = Form(None),

    # Optional.
    customer_email: str | None = Form(None),

    # JSON string containing InvoiceItemCreate[].
    #
    # Example:
    #
    # [
    #   {
    #     "product_name": "Rings",
    #     "item_number": 1,
    #     "unit_price": 250
    #   },
    #   {
    #     "product_name": "Rings",
    #     "item_number": 2,
    #     "unit_price": 400
    #   }
    # ]
    items: str = Form(...),

    product_description: str | None = Form(None),

    tax_percent: float = Form(0),

    discount_amount: float = Form(0),

    notes: str | None = Form(None),

    exhibition_name: str | None = Form(None),

    captured_at: datetime | None = Form(None),

    # REQUIRED.
    photo: UploadFile = File(...),

    db: Session = Depends(get_db),

    agent: Agent = Depends(get_current_agent),
):
    # --------------------------------------------------------
    # Product photo is mandatory
    # --------------------------------------------------------

    if photo is None or not photo.filename:
        raise HTTPException(
            status_code=400,
            detail="Product photo is required.",
        )

    if photo.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported photo type: "
                f"{photo.content_type}"
            ),
        )

    # --------------------------------------------------------
    # Parse items JSON
    # --------------------------------------------------------

    try:
        parsed_items = json.loads(items)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422,
            detail="Invalid items JSON.",
        )

    if not isinstance(parsed_items, list):
        raise HTTPException(
            status_code=422,
            detail="items must be a JSON array.",
        )

    # --------------------------------------------------------
    # Validate request through Pydantic
    # --------------------------------------------------------

    try:
        payload = InvoiceCreate(
            client_uuid=client_uuid,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=(
                customer_email
                or None
            ),
            items=parsed_items,
            product_description=product_description,
            tax_percent=tax_percent,
            discount_amount=discount_amount,
            notes=notes,
            exhibition_name=exhibition_name,
            captured_at=captured_at,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    # --------------------------------------------------------
    # Idempotency
    # --------------------------------------------------------

    existing = (
        db.query(Invoice)
        .filter(
            Invoice.client_uuid
            == payload.client_uuid
        )
        .first()
    )

    if existing:
        return existing

    # --------------------------------------------------------
    # Check photo size
    # --------------------------------------------------------

    photo_bytes = await photo.read()

    if len(photo_bytes) > MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Photo exceeds 8MB limit.",
        )

    # Reset UploadFile so storage.save_upload()
    # can read it again.
    await photo.seek(0)

    # --------------------------------------------------------
    # Save photo
    # --------------------------------------------------------

    photo_path = await storage.save_upload(
        photo,
        "photos",
    )

    # --------------------------------------------------------
    # Prepare invoice data
    # --------------------------------------------------------

    data = payload.model_dump(
        exclude={
            "client_uuid",
        }
    )

    data["captured_at"] = (
        data["captured_at"]
        or datetime.utcnow()
    )

    # --------------------------------------------------------
    # Create invoice + items + PDF + delivery
    # --------------------------------------------------------

    try:
        invoice = create_and_deliver(
            db=db,
            agent=agent,
            data={
                "client_uuid": payload.client_uuid,
                **data,
            },
            photo_relative_path=photo_path,
        )

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    return invoice


# ============================================================
# LIST
# ============================================================


@router.get(
    "",
    response_model=list[InvoiceListItem],
)
def list_invoices(
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    query = db.query(Invoice)

    # Agents see only their own invoices.
    # Admins see all invoices.
    if agent.role != "admin":
        query = query.filter(
            Invoice.agent_id == agent.id
        )

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    if q:
        like = f"%{q}%"

        query = (
            query
            .outerjoin(
                InvoiceItem,
                InvoiceItem.invoice_id
                == Invoice.id,
            )
            .filter(
                or_(
                    Invoice.customer_name.ilike(
                        like
                    ),
                    Invoice.customer_phone.ilike(
                        like
                    ),
                    Invoice.invoice_number.ilike(
                        like
                    ),
                    InvoiceItem.product_name.ilike(
                        like
                    ),
                )
            )
            .distinct()
        )

    return (
        query
        .order_by(
            Invoice.created_at.desc()
        )
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


# ============================================================
# OWNERSHIP
# ============================================================


def _get_owned_invoice(
    db: Session,
    agent: Agent,
    invoice_id: int,
) -> Invoice:
    invoice = db.get(
        Invoice,
        invoice_id,
    )

    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found",
        )

    if (
        agent.role != "admin"
        and invoice.agent_id != agent.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Not your invoice",
        )

    return invoice


# ============================================================
# GET ONE
# ============================================================


@router.get(
    "/{invoice_id}",
    response_model=InvoiceOut,
)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    return _get_owned_invoice(
        db,
        agent,
        invoice_id,
    )


# ============================================================
# RESEND
# ============================================================


@router.post(
    "/{invoice_id}/resend",
    response_model=InvoiceOut,
)
def resend_invoice(
    invoice_id: int,
    payload: ResendRequest | None = None,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    invoice = _get_owned_invoice(
        db,
        agent,
        invoice_id,
    )

    deliver_invoice(
        db,
        invoice,
    )

    db.refresh(invoice)

    return invoice