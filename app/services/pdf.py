"""Generate a branded PDF invoice for a completed sale, including the
product photo, and store it via the storage service."""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.models import Invoice
from app.services import storage

settings = get_settings()

PAGE_W, PAGE_H = A4


def _wrapped_lines(text: str, max_chars: int) -> list[str]:
    words = (text or "").split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) > max_chars:
            if current:
                lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def build_invoice_pdf_bytes(invoice: Invoice) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    left = 20 * mm
    right = PAGE_W - 20 * mm
    y = PAGE_H - 20 * mm

    # --- Header ---
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, settings.COMPANY_NAME)
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(right, y, "INVOICE")
    y -= 7 * mm

    c.setFont("Helvetica", 9)
    if settings.COMPANY_ADDRESS:
        c.drawString(left, y, settings.COMPANY_ADDRESS)
    c.drawRightString(right, y, invoice.invoice_number)
    y -= 5 * mm
    if settings.COMPANY_GSTIN:
        c.drawString(left, y, f"GSTIN: {settings.COMPANY_GSTIN}")
    c.drawRightString(right, y, invoice.created_at.strftime("%d %b %Y, %I:%M %p"))
    y -= 10 * mm

    c.setStrokeColor(colors.HexColor("#cccccc"))
    c.line(left, y, right, y)
    y -= 8 * mm

    # --- Bill To ---
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Billed To")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(left, y, invoice.customer_name)
    y -= 5 * mm
    c.drawString(left, y, invoice.customer_phone)
    y -= 5 * mm
    if invoice.customer_email:
        c.drawString(left, y, invoice.customer_email)
        y -= 5 * mm
    if invoice.exhibition_name:
        c.drawString(left, y, f"Exhibition: {invoice.exhibition_name}")
        y -= 5 * mm

    y -= 6 * mm

    # --- Product photo (if any) ---
    photo_bottom = y
    if invoice.product_photo_path:
        try:
            local_path = None
            if settings.STORAGE_BACKEND == "local":
                local_path = storage.get_storage().absolute_path(invoice.product_photo_path)
            if local_path and local_path.exists():
                img = ImageReader(str(local_path))
                iw, ih = img.getSize()
                max_w, max_h = 55 * mm, 55 * mm
                scale = min(max_w / iw, max_h / ih)
                w, h = iw * scale, ih * scale
                c.drawImage(img, right - w, y - h, width=w, height=h, preserveAspectRatio=True, mask="auto")
                photo_bottom = y - h
        except Exception:
            # Never let a broken/missing image stop invoice generation.
            photo_bottom = y

    # --- Product details table ---
    table_right = right - 60 * mm if invoice.product_photo_path else right
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Product")
    y -= 6 * mm

    c.setFont("Helvetica", 10)
    for line in _wrapped_lines(invoice.product_name, 55):
        c.drawString(left, y, line)
        y -= 5 * mm
    if invoice.product_description:
        c.setFont("Helvetica-Oblique", 9)
        for line in _wrapped_lines(invoice.product_description, 65):
            c.drawString(left, y, line)
            y -= 4.5 * mm
        c.setFont("Helvetica", 10)

    y = min(y, photo_bottom) - 8 * mm

    # --- Line items table ---
    c.setStrokeColor(colors.HexColor("#cccccc"))
    c.line(left, y, right, y)
    y -= 7 * mm

    col_qty = left + 90 * mm
    col_price = left + 120 * mm
    col_total = right

    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Item")
    c.drawString(col_qty, y, "Qty")
    c.drawString(col_price, y, "Unit Price")
    c.drawRightString(col_total, y, "Amount")
    y -= 5 * mm
    c.line(left, y, right, y)
    y -= 6 * mm

    c.setFont("Helvetica", 9)
    for line in _wrapped_lines(invoice.product_name, 45):
        c.drawString(left, y, line)
        y -= 4.5 * mm
    y += 4.5 * mm  # re-align qty/price/total with first line
    c.drawString(col_qty, y, str(invoice.quantity))
    c.drawString(col_price, y, f"{float(invoice.unit_price):,.2f}")
    c.drawRightString(col_total, y, f"{invoice.subtotal:,.2f}")
    y -= 10 * mm

    c.line(left, y, right, y)
    y -= 7 * mm

    def totals_row(label: str, value: str, bold: bool = False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawString(col_price, y, label)
        c.drawRightString(col_total, y, value)
        y -= 6 * mm

    totals_row("Subtotal", f"{invoice.subtotal:,.2f}")
    if float(invoice.tax_percent) > 0:
        totals_row(f"Tax ({float(invoice.tax_percent):g}%)", f"{invoice.tax_amount:,.2f}")
    if float(invoice.discount_amount) > 0:
        totals_row("Discount", f"-{float(invoice.discount_amount):,.2f}")
    totals_row("Total", f"{invoice.total:,.2f}", bold=True)

    if invoice.notes:
        y -= 8 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, "Notes")
        y -= 5 * mm
        c.setFont("Helvetica", 9)
        for line in _wrapped_lines(invoice.notes, 90):
            c.drawString(left, y, line)
            y -= 4.5 * mm

    # --- Footer ---
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(PAGE_W / 2, 15 * mm, "Thank you for your purchase! Generated automatically at the booth.")

    c.showPage()
    c.save()
    return buf.getvalue()


def generate_and_store_invoice_pdf(invoice: Invoice) -> str:
    pdf_bytes = build_invoice_pdf_bytes(invoice)
    filename = f"{invoice.invoice_number}.pdf"
    return storage.save_bytes(pdf_bytes, "invoices", filename)
