"""
Generate a branded PDF invoice for a completed sale.

The invoice can contain multiple individually priced items.

Example:

    Product       Item       Price
    --------------------------------
    Ring          #1         ₹250.00
    Ring          #2         ₹400.00
    Bracelet      #1         ₹300.00

The product photo is displayed above the item table.

Prices are NEVER taken from a fixed product catalog.
Every price comes directly from the invoice item entered
by the booth agent.
"""

from __future__ import annotations

from decimal import Decimal
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


# ============================================================
# HELPERS
# ============================================================


def _wrapped_lines(
    text: str | None,
    max_chars: int,
) -> list[str]:
    """
    Wrap long text into multiple PDF lines.
    """

    words = (text or "").split()

    if not words:
        return [""]

    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        if len(candidate) > max_chars:
            if current:
                lines.append(current)

            current = word
        else:
            current = candidate

    if current:
        lines.append(current)

    return lines


def _money(
    value: Decimal | float | int,
) -> str:
    """
    Format monetary values consistently.
    """

    return f"{float(value):,.2f}"


# ============================================================
# PDF GENERATION
# ============================================================


def build_invoice_pdf_bytes(
    invoice: Invoice,
) -> bytes:
    """
    Build the complete invoice PDF.

    Layout:

        Company
        Invoice number/date

        Customer details

        Product photo

        Product items
        --------------------------------
        Product       Item       Price

        Rings         #1         250.00
        Rings         #2         400.00
        Necklace      #1         600.00

        Subtotal
        Tax
        Discount
        Total

        Notes
        Footer
    """

    buffer = BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4,
    )

    left = 20 * mm
    right = PAGE_W - 20 * mm

    y = PAGE_H - 20 * mm

    # ========================================================
    # HEADER
    # ========================================================

    pdf.setFillColor(
        colors.HexColor("#111827")
    )

    pdf.setFont(
        "Helvetica-Bold",
        18,
    )

    pdf.drawString(
        left,
        y,
        settings.COMPANY_NAME,
    )

    pdf.setFont(
        "Helvetica-Bold",
        16,
    )

    pdf.drawRightString(
        right,
        y,
        "INVOICE",
    )

    y -= 7 * mm

    # Company address
    pdf.setFont(
        "Helvetica",
        9,
    )

    if settings.COMPANY_ADDRESS:
        pdf.drawString(
            left,
            y,
            settings.COMPANY_ADDRESS,
        )

    pdf.drawRightString(
        right,
        y,
        invoice.invoice_number,
    )

    y -= 5 * mm

    # GST
    if settings.COMPANY_GSTIN:
        pdf.drawString(
            left,
            y,
            f"GSTIN: {settings.COMPANY_GSTIN}",
        )

    pdf.drawRightString(
        right,
        y,
        invoice.created_at.strftime(
            "%d %b %Y, %I:%M %p"
        ),
    )

    y -= 10 * mm

    pdf.setStrokeColor(
        colors.HexColor("#D1D5DB")
    )

    pdf.line(
        left,
        y,
        right,
        y,
    )

    y -= 8 * mm

    # ========================================================
    # CUSTOMER DETAILS
    # ========================================================

    pdf.setFillColor(
        colors.HexColor("#111827")
    )

    pdf.setFont(
        "Helvetica-Bold",
        11,
    )

    pdf.drawString(
        left,
        y,
        "Billed To",
    )

    y -= 6 * mm

    pdf.setFont(
        "Helvetica",
        10,
    )

    # Customer name
    pdf.drawString(
        left,
        y,
        invoice.customer_name,
    )

    y -= 5 * mm

    # Phone is optional.
    if invoice.customer_phone:

        pdf.drawString(
            left,
            y,
            invoice.customer_phone,
        )

        y -= 5 * mm

    # Email is optional.
    if invoice.customer_email:

        pdf.drawString(
            left,
            y,
            str(invoice.customer_email),
        )

        y -= 5 * mm

    # Exhibition is optional.
    if invoice.exhibition_name:

        pdf.drawString(
            left,
            y,
            f"Exhibition: {invoice.exhibition_name}",
        )

        y -= 5 * mm

    y -= 6 * mm

    # ========================================================
    # PRODUCT PHOTO
    # ========================================================

    photo_bottom = y

    if invoice.product_photo_path:

        try:

            local_path = None

            if settings.STORAGE_BACKEND == "local":

                local_path = (
                    storage
                    .get_storage()
                    .absolute_path(
                        invoice.product_photo_path
                    )
                )

            if local_path and local_path.exists():

                image = ImageReader(
                    str(local_path)
                )

                image_width, image_height = (
                    image.getSize()
                )

                max_width = 70 * mm
                max_height = 60 * mm

                scale = min(
                    max_width / image_width,
                    max_height / image_height,
                )

                width = image_width * scale
                height = image_height * scale

                # Center image.
                image_x = (
                    PAGE_W - width
                ) / 2

                image_y = y - height

                # Image border.
                pdf.setStrokeColor(
                    colors.HexColor("#D1D5DB")
                )

                pdf.roundRect(
                    image_x - 2 * mm,
                    image_y - 2 * mm,
                    width + 4 * mm,
                    height + 4 * mm,
                    2 * mm,
                    stroke=1,
                    fill=0,
                )

                pdf.drawImage(
                    image,
                    image_x,
                    image_y,
                    width=width,
                    height=height,
                    preserveAspectRatio=True,
                    mask="auto",
                )

                photo_bottom = (
                    image_y - 4 * mm
                )

        except Exception:
            # Broken/missing image must never prevent
            # invoice PDF generation.
            photo_bottom = y

    # Move below image.
    y = photo_bottom - 8 * mm

    # ========================================================
    # PRODUCTS SECTION
    # ========================================================

    pdf.setFillColor(
        colors.HexColor("#111827")
    )

    pdf.setFont(
        "Helvetica-Bold",
        11,
    )

    pdf.drawString(
        left,
        y,
        "Products",
    )

    y -= 6 * mm

    # ========================================================
    # PRODUCT DESCRIPTION
    # ========================================================

    if invoice.product_description:

        pdf.setFont(
            "Helvetica-Oblique",
            9,
        )

        pdf.setFillColor(
            colors.HexColor("#4B5563")
        )

        for line in _wrapped_lines(
            invoice.product_description,
            90,
        ):

            pdf.drawString(
                left,
                y,
                line,
            )

            y -= 4.5 * mm

        y -= 3 * mm

    # ========================================================
    # ITEMS TABLE
    # ========================================================

    # Column positions.
    col_product = left
    col_item = left + 105 * mm
    col_price = right

    # Header.
    pdf.setFillColor(
        colors.HexColor("#374151")
    )

    pdf.setFont(
        "Helvetica-Bold",
        9,
    )

    pdf.drawString(
        col_product,
        y,
        "Product",
    )

    pdf.drawString(
        col_item,
        y,
        "Item",
    )

    pdf.drawRightString(
        col_price,
        y,
        "Price",
    )

    y -= 4 * mm

    pdf.setStrokeColor(
        colors.HexColor("#D1D5DB")
    )

    pdf.line(
        left,
        y,
        right,
        y,
    )

    y -= 6 * mm

    # ========================================================
    # ITEM ROWS
    # ========================================================

    pdf.setFillColor(
        colors.HexColor("#111827")
    )

    pdf.setFont(
        "Helvetica",
        9,
    )

    for invoice_item in invoice.items:

        product_lines = _wrapped_lines(
            invoice_item.product_name,
            55,
        )

        # Product name can occupy multiple lines.
        for line_index, product_line in enumerate(
            product_lines
        ):

            pdf.drawString(
                col_product,
                y,
                product_line,
            )

            # Item number and price appear only
            # on the first product line.
            if line_index == 0:

                pdf.drawString(
                    col_item,
                    y,
                    f"#{invoice_item.item_number}",
                )

                pdf.drawRightString(
                    col_price,
                    y,
                    _money(
                        invoice_item.unit_price
                    ),
                )

            y -= 4.5 * mm

        # Space between rows.
        y -= 2 * mm

    # ========================================================
    # TABLE BORDER
    # ========================================================

    pdf.setStrokeColor(
        colors.HexColor("#D1D5DB")
    )

    pdf.line(
        left,
        y,
        right,
        y,
    )

    y -= 8 * mm

    # ========================================================
    # TOTALS
    # ========================================================

    col_label = left + 105 * mm

    def totals_row(
        label: str,
        value: str,
        bold: bool = False,
    ) -> None:

        nonlocal y

        pdf.setFillColor(
            colors.HexColor("#111827")
        )

        pdf.setFont(
            "Helvetica-Bold"
            if bold
            else "Helvetica",
            10,
        )

        pdf.drawString(
            col_label,
            y,
            label,
        )

        pdf.drawRightString(
            col_price,
            y,
            value,
        )

        y -= 6 * mm

    # Subtotal.
    totals_row(
        "Subtotal",
        _money(invoice.subtotal),
    )

    # Tax.
    if invoice.tax_percent > 0:

        totals_row(
            f"Tax ({float(invoice.tax_percent):g}%)",
            _money(invoice.tax_amount),
        )

    # Discount.
    if invoice.discount_amount > 0:

        totals_row(
            "Discount",
            f"-{_money(invoice.discount_amount)}",
        )

    # Separator.
    pdf.setStrokeColor(
        colors.HexColor("#9CA3AF")
    )

    pdf.line(
        col_label,
        y + 2 * mm,
        right,
        y + 2 * mm,
    )

    y -= 3 * mm

    # Grand total.
    totals_row(
        "Total",
        _money(invoice.total),
        bold=True,
    )

    # ========================================================
    # NOTES
    # ========================================================

    if invoice.notes:

        y -= 8 * mm

        pdf.setFillColor(
            colors.HexColor("#111827")
        )

        pdf.setFont(
            "Helvetica-Bold",
            10,
        )

        pdf.drawString(
            left,
            y,
            "Notes",
        )

        y -= 5 * mm

        pdf.setFont(
            "Helvetica",
            9,
        )

        for line in _wrapped_lines(
            invoice.notes,
            90,
        ):

            pdf.drawString(
                left,
                y,
                line,
            )

            y -= 4.5 * mm

    # ========================================================
    # FOOTER
    # ========================================================

    pdf.setFont(
        "Helvetica-Oblique",
        8,
    )

    pdf.setFillColor(
        colors.grey
    )

    pdf.drawCentredString(
        PAGE_W / 2,
        15 * mm,
        (
            "Thank you for your purchase! "
            "Generated automatically at the booth."
        ),
    )

    # ========================================================
    # FINISH
    # ========================================================

    pdf.showPage()
    pdf.save()

    return buffer.getvalue()


# ============================================================
# STORE PDF
# ============================================================


def generate_and_store_invoice_pdf(
    invoice: Invoice,
) -> str:
    """
    Generate the invoice PDF and store it through
    the configured storage backend.
    """

    pdf_bytes = build_invoice_pdf_bytes(
        invoice
    )

    filename = (
        f"{invoice.invoice_number}.pdf"
    )

    return storage.save_bytes(
        pdf_bytes,
        "invoices",
        filename,
    )