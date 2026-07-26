"""
Invoice CRUD for the "online" happy path: agent is connected and submits the
form (with photo) directly. For offline-captured invoices, see routers/sync.py.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_agent
from app.models import Agent, Invoice
from app.schemas import InvoiceCreate, InvoiceListItem, InvoiceOut, ResendRequest
from app.services import storage
from app.services.invoice_service import create_and_deliver, deliver_invoice

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

MAX_PHOTO_BYTES = 8 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    client_uuid: str = Form(...),
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_email: str | None = Form(None),
    product_name: str = Form(...),
    product_description: str | None = Form(None),
    quantity: int = Form(1),
    unit_price: float = Form(0),
    tax_percent: float = Form(0),
    discount_amount: float = Form(0),
    notes: str | None = Form(None),
    exhibition_name: str | None = Form(None),
    captured_at: datetime | None = Form(None),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    payload = InvoiceCreate(
        client_uuid=client_uuid,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email or None,
        product_name=product_name,
        product_description=product_description,
        quantity=quantity,
        unit_price=unit_price,
        tax_percent=tax_percent,
        discount_amount=discount_amount,
        notes=notes,
        exhibition_name=exhibition_name,
        captured_at=captured_at,
    )

    existing = db.query(Invoice).filter(Invoice.client_uuid == payload.client_uuid).first()
    if existing:
        return existing

    photo_path = None
    if photo is not None and photo.filename:
        if photo.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported photo type: {photo.content_type}")
        photo_path = await storage.save_upload(photo, "photos")

    data = payload.model_dump(exclude={"client_uuid"})
    data["captured_at"] = data["captured_at"] or datetime.utcnow()
    invoice = create_and_deliver(
        db,
        agent,
        {"client_uuid": payload.client_uuid, **data},
        photo_path,
    )
    return invoice


@router.get("", response_model=list[InvoiceListItem])
def list_invoices(
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    query = db.query(Invoice)
    if agent.role != "admin":
        query = query.filter(Invoice.agent_id == agent.id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Invoice.customer_name.ilike(like))
            | (Invoice.customer_phone.ilike(like))
            | (Invoice.invoice_number.ilike(like))
            | (Invoice.product_name.ilike(like))
        )
    return query.order_by(Invoice.created_at.desc()).offset(offset).limit(min(limit, 200)).all()


def _get_owned_invoice(db: Session, agent: Agent, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if agent.role != "admin" and invoice.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not your invoice")
    return invoice


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), agent: Agent = Depends(get_current_agent)):
    return _get_owned_invoice(db, agent, invoice_id)


@router.post("/{invoice_id}/resend", response_model=InvoiceOut)
def resend_invoice(
    invoice_id: int,
    payload: ResendRequest | None = None,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    invoice = _get_owned_invoice(db, agent, invoice_id)
    deliver_invoice(db, invoice)
    db.refresh(invoice)
    return invoice
