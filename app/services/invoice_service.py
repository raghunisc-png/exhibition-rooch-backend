"""
Core invoice workflow shared by the online-create endpoint and the
offline batch-sync endpoint.

An invoice can contain multiple individually priced items.

Example:

    Rings #1      ₹250
    Rings #2      ₹400
    Necklace #1   ₹600

There is NO fixed product price.

The price always comes from the individual item entered
by the booth agent.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    Agent,
    Invoice,
    InvoiceItem,
    MessageChannel,
    MessageLog,
    MessageStatus,
)
from app.services import pdf as pdf_service
from app.services import storage
from app.services.messaging import (
    send_sms_invoice,
    send_whatsapp_invoice,
)
from app.services.numbering import generate_invoice_number


logger = logging.getLogger("invoice_service")


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
    Create the invoice row and all individual invoice items.

    Expected data:

        {
            "client_uuid": "...",
            "customer_name": "Priya",
            "customer_phone": "+919876543210",
            "customer_email": "...",

            "items": [
                {
                    "product_name": "Rings",
                    "item_number": 1,
                    "unit_price": 250
                },
                {
                    "product_name": "Rings",
                    "item_number": 2,
                    "unit_price": 400
                },
                {
                    "product_name": "Necklace",
                    "item_number": 1,
                    "unit_price": 600
                }
            ],

            "tax_percent": 0,
            "discount_amount": 0,
            ...
        }

    Product photo is mandatory.
    Individual item prices are stored in invoice_items.
    """

    # --------------------------------------------------------
    # Product photo is mandatory
    # --------------------------------------------------------

    if not photo_relative_path:
        raise ValueError(
            "Product photo is required."
        )

    # --------------------------------------------------------
    # Extract items before creating Invoice
    #
    # Invoice itself does NOT have an `items` database column.
    # Items are stored in invoice_items.
    # --------------------------------------------------------

    items_data = data.pop("items", None)

    if not items_data:
        raise ValueError(
            "At least one invoice item is required."
        )

    # --------------------------------------------------------
    # Create invoice
    # --------------------------------------------------------

    invoice = Invoice(
        agent_id=agent.id,
        invoice_number=generate_invoice_number(db),
        product_photo_path=photo_relative_path,
        **data,
    )

    db.add(invoice)

    # Flush so invoice.id is available for InvoiceItem rows.
    db.flush()

    # --------------------------------------------------------
    # Create individual invoice items
    # --------------------------------------------------------

    for item_data in items_data:
        product_name = str(
            item_data["product_name"]
        ).strip()

        if not product_name:
            raise ValueError(
                "Product name cannot be empty."
            )

        item_number = int(
            item_data["item_number"]
        )

        if item_number < 1 or item_number > 5:
            raise ValueError(
                "Item number must be between 1 and 5."
            )

        unit_price = Decimal(
            str(item_data["unit_price"])
        )

        if unit_price < Decimal("0.00"):
            raise ValueError(
                "Product price cannot be negative."
            )

        invoice_item = InvoiceItem(
            invoice_id=invoice.id,
            product_name=product_name,
            item_number=item_number,
            unit_price=unit_price,
        )

        db.add(invoice_item)

    # --------------------------------------------------------
    # Commit invoice + items together
    # --------------------------------------------------------

    db.commit()

    db.refresh(invoice)

    return invoice


# ============================================================
# PDF
# ============================================================


def render_pdf(
    db: Session,
    invoice: Invoice,
) -> None:
    """
    Generate the PDF and store its path on the invoice.
    """

    relative_path = (
        pdf_service.generate_and_store_invoice_pdf(
            invoice
        )
    )

    invoice.pdf_path = relative_path

    db.commit()
    db.refresh(invoice)


# ============================================================
# MESSAGE LOG
# ============================================================


def _log_message(
    db: Session,
    invoice: Invoice,
    channel: MessageChannel,
    status: MessageStatus,
    provider_sid: str | None = None,
    error_message: str | None = None,
) -> MessageLog:
    """
    Store one WhatsApp/SMS delivery attempt.
    """

    log = MessageLog(
        invoice_id=invoice.id,
        channel=channel,
        status=status,
        provider_sid=provider_sid,
        error_message=error_message,
    )

    db.add(log)

    db.commit()

    return log


# ============================================================
# DELIVERY
# ============================================================


def deliver_invoice(
    db: Session,
    invoice: Invoice,
) -> None:
    """
    Deliver the invoice PDF.

    Delivery order:

        1. Generate PDF if necessary
        2. If phone does not exist -> skip messaging
        3. Try WhatsApp
        4. If WhatsApp fails -> SMS fallback

    Phone number is optional in the new application.
    """

    # --------------------------------------------------------
    # Make sure PDF exists
    # --------------------------------------------------------

    if not invoice.pdf_path:
        render_pdf(
            db,
            invoice,
        )

    # --------------------------------------------------------
    # No phone number
    # --------------------------------------------------------

    if not invoice.customer_phone:
        _log_message(
            db=db,
            invoice=invoice,
            channel=MessageChannel.whatsapp,
            status=MessageStatus.skipped,
            error_message=(
                "Customer phone number was not provided."
            ),
        )

        return

    # --------------------------------------------------------
    # Public PDF URL
    # --------------------------------------------------------

    pdf_url = storage.public_url(
        invoice.pdf_path
    )

    # --------------------------------------------------------
    # WhatsApp
    # --------------------------------------------------------

    try:
        wa_result = send_whatsapp_invoice(
            invoice,
            pdf_url,
        )

        _log_message(
            db=db,
            invoice=invoice,
            channel=MessageChannel.whatsapp,
            status=(
                MessageStatus.sent
                if wa_result.ok
                else MessageStatus.failed
            ),
            provider_sid=wa_result.provider_sid,
            error_message=wa_result.error,
        )

        # WhatsApp succeeded.
        if wa_result.ok:
            return

    except Exception as exc:
        logger.exception(
            "WhatsApp delivery failed for invoice %s",
            invoice.invoice_number,
        )

        _log_message(
            db=db,
            invoice=invoice,
            channel=MessageChannel.whatsapp,
            status=MessageStatus.failed,
            error_message=str(exc),
        )

    # --------------------------------------------------------
    # SMS fallback
    # --------------------------------------------------------

    try:
        sms_result = send_sms_invoice(
            invoice,
            pdf_url,
        )

        _log_message(
            db=db,
            invoice=invoice,
            channel=MessageChannel.sms,
            status=(
                MessageStatus.sent
                if sms_result.ok
                else MessageStatus.failed
            ),
            provider_sid=sms_result.provider_sid,
            error_message=sms_result.error,
        )

    except Exception as exc:
        logger.exception(
            "SMS delivery failed for invoice %s",
            invoice.invoice_number,
        )

        _log_message(
            db=db,
            invoice=invoice,
            channel=MessageChannel.sms,
            status=MessageStatus.failed,
            error_message=str(exc),
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

    Steps:

        1. Create invoice
        2. Create individual invoice items
        3. Commit invoice
        4. Generate PDF
        5. Attempt WhatsApp
        6. Fall back to SMS

    Important:

    If PDF or messaging fails, the invoice itself remains
    committed in the database.

    The agent can retry delivery later using the resend
    endpoint.
    """

    invoice = create_invoice_row(
        db=db,
        agent=agent,
        data=data,
        photo_relative_path=photo_relative_path,
    )

    try:
        # ----------------------------------------------------
        # Generate PDF
        # ----------------------------------------------------

        render_pdf(
            db,
            invoice,
        )

        # ----------------------------------------------------
        # Deliver invoice
        # ----------------------------------------------------

        deliver_invoice(
            db,
            invoice,
        )

    except Exception:
        logger.exception(
            "PDF/delivery step failed for invoice %s",
            invoice.invoice_number,
        )

    return invoice