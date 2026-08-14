"""
Twilio-backed WhatsApp + SMS delivery.

The application supports:

- Optional customer phone number.
- WhatsApp delivery when a phone number is available.
- SMS fallback when WhatsApp fails.
- No messaging when the customer did not provide a phone number.
- Invoice messages containing multiple individually priced items.

Product prices are never taken from a fixed catalog.
They come directly from InvoiceItem.unit_price.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import get_settings
from app.models import Invoice


logger = logging.getLogger("messaging")

settings = get_settings()


# ============================================================
# SEND RESULT
# ============================================================


@dataclass
class SendResult:
    """
    Result returned after attempting a WhatsApp/SMS send.
    """

    ok: bool

    provider_sid: str | None = None

    error: str | None = None


# ============================================================
# TWILIO CLIENT
# ============================================================


def _client() -> Client:
    """
    Create the Twilio client.
    """

    return Client(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN,
    )


# ============================================================
# INVOICE MESSAGE
# ============================================================


def _invoice_message_body(
    invoice: Invoice,
    pdf_url: str,
) -> str:
    """
    Build the customer-facing invoice message.

    The invoice can contain multiple individually priced
    products.

    Example:

        Rings #1 - ₹250.00
        Rings #2 - ₹400.00
        Necklace #1 - ₹600.00
    """

    lines: list[str] = []

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    lines.append(
        f"Hi {invoice.customer_name},"
    )

    lines.append(
        "Thank you for your purchase!"
    )

    if invoice.exhibition_name:
        lines.append(
            f"Exhibition: {invoice.exhibition_name}"
        )

    lines.append("")

    # --------------------------------------------------------
    # Invoice number
    # --------------------------------------------------------

    lines.append(
        f"Invoice: {invoice.invoice_number}"
    )

    lines.append("")

    # --------------------------------------------------------
    # Items
    # --------------------------------------------------------

    lines.append("Items:")

    for item in invoice.items:

        lines.append(
            f"- {item.product_name or 'Item'} "
            f"#{item.item_number}: "
            f"₹{float(item.unit_price):,.2f}"
        )

    # --------------------------------------------------------
    # Totals
    # --------------------------------------------------------

    lines.append("")

    lines.append(
        f"Subtotal: ₹{float(invoice.subtotal):,.2f}"
    )

    if float(invoice.tax_percent) > 0:
        lines.append(
            f"Tax ({float(invoice.tax_percent):g}%): "
            f"₹{float(invoice.tax_amount):,.2f}"
        )

    if float(invoice.discount_amount) > 0:
        lines.append(
            f"Discount: "
            f"-₹{float(invoice.discount_amount):,.2f}"
        )

    lines.append(
        f"Total: ₹{float(invoice.total):,.2f}"
    )

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    lines.append("")

    lines.append(
        f"Download your invoice: {pdf_url}"
    )

    return "\n".join(lines)


# ============================================================
# WHATSAPP
# ============================================================


def send_whatsapp_invoice(
    invoice: Invoice,
    pdf_url: str,
) -> SendResult:
    """
    Send the invoice through WhatsApp.

    Phone number is optional.

    If there is no phone number, this function safely
    skips the operation.
    """

    # --------------------------------------------------------
    # Phone is optional
    # --------------------------------------------------------

    if not invoice.customer_phone:
        return SendResult(
            ok=False,
            error=(
                "Customer phone number was not provided."
            ),
        )

    # --------------------------------------------------------
    # Twilio configuration
    # --------------------------------------------------------

    if not settings.messaging_configured:
        return SendResult(
            ok=False,
            error=(
                "Twilio is not configured "
                "(missing account SID/auth token)"
            ),
        )

    if not settings.TWILIO_WHATSAPP_FROM:
        return SendResult(
            ok=False,
            error=(
                "Twilio WhatsApp sender is not configured."
            ),
        )

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    to = (
        f"whatsapp:{invoice.customer_phone}"
    )

    try:

        message = _client().messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=to,
            body=_invoice_message_body(
                invoice,
                pdf_url,
            ),
            media_url=[pdf_url],
        )

        return SendResult(
            ok=True,
            provider_sid=message.sid,
        )

    except TwilioRestException as exc:

        logger.warning(
            "WhatsApp send failed for invoice %s: %s",
            invoice.invoice_number,
            exc,
        )

        return SendResult(
            ok=False,
            error=str(exc),
        )

    except Exception as exc:

        logger.exception(
            "Unexpected WhatsApp error for invoice %s",
            invoice.invoice_number,
        )

        return SendResult(
            ok=False,
            error=str(exc),
        )


# ============================================================
# SMS
# ============================================================


def send_sms_invoice(
    invoice: Invoice,
    pdf_url: str,
) -> SendResult:
    """
    Send the invoice through SMS.

    SMS is used as the fallback when WhatsApp fails.

    Phone number is optional.
    """

    # --------------------------------------------------------
    # Phone is optional
    # --------------------------------------------------------

    if not invoice.customer_phone:
        return SendResult(
            ok=False,
            error=(
                "Customer phone number was not provided."
            ),
        )

    # --------------------------------------------------------
    # Twilio configuration
    # --------------------------------------------------------

    if not settings.messaging_configured:
        return SendResult(
            ok=False,
            error=(
                "Twilio is not configured "
                "(missing account SID/auth token)"
            ),
        )

    if not settings.TWILIO_SMS_FROM:
        return SendResult(
            ok=False,
            error=(
                "Twilio SMS sender is not configured."
            ),
        )

    # --------------------------------------------------------
    # Send SMS
    # --------------------------------------------------------

    try:

        message = _client().messages.create(
            from_=settings.TWILIO_SMS_FROM,
            to=invoice.customer_phone,
            body=_invoice_message_body(
                invoice,
                pdf_url,
            ),
        )

        return SendResult(
            ok=True,
            provider_sid=message.sid,
        )

    except TwilioRestException as exc:

        logger.warning(
            "SMS send failed for invoice %s: %s",
            invoice.invoice_number,
            exc,
        )

        return SendResult(
            ok=False,
            error=str(exc),
        )

    except Exception as exc:

        logger.exception(
            "Unexpected SMS error for invoice %s",
            invoice.invoice_number,
        )

        return SendResult(
            ok=False,
            error=str(exc),
        )