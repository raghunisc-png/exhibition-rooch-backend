"""
Core invoice workflow shared by the single-create endpoint and the offline
batch-sync endpoint: create the DB row, render the PDF, then attempt
WhatsApp delivery with an SMS fallback.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import Agent, Invoice, MessageChannel, MessageLog, MessageStatus
from app.services import pdf as pdf_service
from app.services import storage
from app.services.messaging import send_sms_invoice, send_whatsapp_invoice
from app.services.numbering import generate_invoice_number

logger = logging.getLogger("invoice_service")


def create_invoice_row(db: Session, agent: Agent, data: dict, photo_relative_path: str | None) -> Invoice:
    invoice = Invoice(
        agent_id=agent.id,
        invoice_number=generate_invoice_number(db),
        product_photo_path=photo_relative_path,
        **data,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def render_pdf(db: Session, invoice: Invoice) -> None:
    relative_path = pdf_service.generate_and_store_invoice_pdf(invoice)
    invoice.pdf_path = relative_path
    db.commit()
    db.refresh(invoice)


def deliver_invoice(db: Session, invoice: Invoice) -> None:
    """Try WhatsApp first; fall back to SMS if WhatsApp isn't usable/fails."""
    if not invoice.pdf_path:
        render_pdf(db, invoice)

    pdf_url = storage.public_url(invoice.pdf_path)

    wa_result = send_whatsapp_invoice(invoice, pdf_url)
    log = MessageLog(
        invoice_id=invoice.id,
        channel=MessageChannel.whatsapp,
        status=MessageStatus.sent if wa_result.ok else MessageStatus.failed,
        provider_sid=wa_result.provider_sid,
        error_message=wa_result.error,
    )
    db.add(log)
    db.commit()

    if wa_result.ok:
        return

    sms_result = send_sms_invoice(invoice, pdf_url)
    log = MessageLog(
        invoice_id=invoice.id,
        channel=MessageChannel.sms,
        status=MessageStatus.sent if sms_result.ok else MessageStatus.failed,
        provider_sid=sms_result.provider_sid,
        error_message=sms_result.error,
    )
    db.add(log)
    db.commit()


def create_and_deliver(db: Session, agent: Agent, data: dict, photo_relative_path: str | None) -> Invoice:
    invoice = create_invoice_row(db, agent, data, photo_relative_path)
    try:
        render_pdf(db, invoice)
        deliver_invoice(db, invoice)
    except Exception:
        # The invoice record itself is already committed; log and let the
        # caller/agent retry delivery via the resend endpoint.
        logger.exception("PDF/delivery step failed for invoice %s", invoice.invoice_number)
    return invoice
