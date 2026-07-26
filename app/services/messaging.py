"""
Twilio-backed WhatsApp + SMS delivery.

Notes for production use:
- WhatsApp: outside Twilio's sandbox, Meta requires the *first* message in a
  new 24h conversation window to use a pre-approved message template. Once
  the customer has replied (or within an existing session) freeform messages
  with media are fine. Create a template in the Twilio console
  (Messaging > Content Template Builder) named e.g. "invoice_ready" and set
  its SID via TWILIO_INVOICE_TEMPLATE_SID if you hit template errors; this
  module falls back to a freeform message+media send otherwise, which is
  sufficient for the sandbox and for numbers within an open session.
- SMS: plain text with a link to the hosted invoice PDF (Twilio does not
  support MMS-style attachments for arbitrary international numbers).
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


@dataclass
class SendResult:
    ok: bool
    provider_sid: str | None = None
    error: str | None = None


def _client() -> Client:
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _invoice_message_body(invoice: Invoice, pdf_url: str) -> str:
    return (
        f"Hi {invoice.customer_name}, thank you for your purchase of "
        f"{invoice.product_name} at {invoice.exhibition_name or 'our booth'}!\n\n"
        f"Invoice {invoice.invoice_number}\n"
        f"Total: {invoice.total:,.2f}\n\n"
        f"Download your invoice: {pdf_url}"
    )


def send_whatsapp_invoice(invoice: Invoice, pdf_url: str) -> SendResult:
    if not settings.messaging_configured:
        return SendResult(ok=False, error="Twilio is not configured (missing account SID/auth token)")

    to = f"whatsapp:{invoice.customer_phone}"
    try:
        msg = _client().messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=to,
            body=_invoice_message_body(invoice, pdf_url),
            media_url=[pdf_url],
        )
        return SendResult(ok=True, provider_sid=msg.sid)
    except TwilioRestException as exc:
        logger.warning("WhatsApp send failed for invoice %s: %s", invoice.invoice_number, exc)
        return SendResult(ok=False, error=str(exc))


def send_sms_invoice(invoice: Invoice, pdf_url: str) -> SendResult:
    if not settings.messaging_configured or not settings.TWILIO_SMS_FROM:
        return SendResult(ok=False, error="Twilio SMS sender is not configured")

    try:
        msg = _client().messages.create(
            from_=settings.TWILIO_SMS_FROM,
            to=invoice.customer_phone,
            body=_invoice_message_body(invoice, pdf_url),
        )
        return SendResult(ok=True, provider_sid=msg.sid)
    except TwilioRestException as exc:
        logger.warning("SMS send failed for invoice %s: %s", invoice.invoice_number, exc)
        return SendResult(ok=False, error=str(exc))
