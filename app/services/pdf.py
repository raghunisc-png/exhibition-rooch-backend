"""
Rooch branded invoice PDF generation.

Features:
- Rooch branded invoice
- Professional A4 layout
- ROOCH branding
- Customer details
- Exhibition ship-to
- Payment mode
- Product photo
- Product table
- Total items
- Subtotal
- Discount
- GST breakup
- Grand total
- PDF storage

Important:
- Existing invoice calculations are preserved.
- Product image keeps its original aspect ratio.
- Invoice content automatically moves to a new page
  when there is not enough vertical space.
- Product table header repeats when the table continues
  onto another page.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

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
# ROOCH BRAND COLORS
# ============================================================

ROOCH_MAROON = colors.HexColor("#810B38")
ROOCH_MAROON_DARK = colors.HexColor("#68082D")
ROOCH_MAROON_LIGHT = colors.HexColor("#A21B4E")

ROOCH_GOLD = colors.HexColor("#B08A45")
ROOCH_GOLD_DARK = colors.HexColor("#8F6B2F")
ROOCH_GOLD_LIGHT = colors.HexColor("#D8BD87")

ROOCH_BLACK = colors.HexColor("#171512")
ROOCH_TEXT = colors.HexColor("#292722")
ROOCH_MUTED = colors.HexColor("#777269")
ROOCH_SOFT_TEXT = colors.HexColor("#9B958A")

ROOCH_CREAM = colors.HexColor("#FAF8F3")
ROOCH_IVORY = colors.HexColor("#F5F1E8")
ROOCH_BEIGE = colors.HexColor("#EEE8DC")

ROOCH_BORDER = colors.HexColor("#E3DDD1")
ROOCH_BORDER_DARK = colors.HexColor("#D7CCBA")

ROOCH_WHITE = colors.white

ROOCH_SUCCESS = colors.HexColor("#16834B")


# ============================================================
# CONSTANTS
# ============================================================

MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")

# Minimum safe area from bottom of page.
# Footer occupies the bottom area, so invoice content
# should never enter this region.
CONTENT_BOTTOM_LIMIT = 30 * mm

# When the remaining content is smaller than this amount,
# financial information is moved to a new page.
FINANCIAL_MIN_SPACE = 82 * mm


# ============================================================
# MONEY HELPER
# ============================================================

def _money(
    value: Decimal | float | int | None,
) -> str:
    """
    Format money consistently to two decimal places.
    """

    if value is None:
        value = Decimal("0.00")

    try:
        decimal_value = Decimal(str(value))
    except Exception:
        decimal_value = Decimal("0.00")

    decimal_value = decimal_value.quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )

    return f"{decimal_value:,.2f}"


# ============================================================
# TEXT WRAPPING
# ============================================================

def _wrapped_lines(
    text: str | None,
    max_chars: int,
) -> list[str]:
    """
    Wrap text into PDF-friendly lines.
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


# ============================================================
# PAYMENT MODE
# ============================================================

def _payment_text(
    invoice: Invoice,
) -> str:
    """
    Return readable payment mode.
    """

    payment_mode = getattr(
        invoice,
        "payment_mode",
        None,
    )

    if payment_mode is None:
        return ""

    value = getattr(
        payment_mode,
        "value",
        payment_mode,
    )

    value = str(value)

    if value.lower() == "online":
        return "Online"

    if value.lower() == "cash":
        return "Cash"

    return value.title()


# ============================================================
# DATE HELPERS
# ============================================================

def _format_date(
    value,
) -> str:

    if not value:
        return ""

    try:
        return value.strftime("%d %b %Y")
    except Exception:
        return str(value)


def _format_datetime(
    value,
) -> str:

    if not value:
        return ""

    try:
        return value.strftime(
            "%d %b %Y, %I:%M %p"
        )
    except Exception:
        return str(value)


# ============================================================
# LOGO
# ============================================================

def _find_logo_path() -> Path | None:
    """
    Find Rooch logo.

    Supports:
    1. COMPANY_LOGO_PATH
    2. Frontend public folder
    3. Backend fallback locations
    """

    configured_path = getattr(
        settings,
        "COMPANY_LOGO_PATH",
        None,
    )

    if configured_path:

        configured = Path(
            str(configured_path)
        )

        if configured.is_file():
            return configured.resolve()

        cwd_path = (
            Path.cwd()
            / configured
        )

        if cwd_path.is_file():
            return cwd_path.resolve()

    try:

        project_root = (
            Path(__file__)
            .resolve()
            .parents[3]
        )

    except IndexError:

        project_root = Path.cwd()

    frontend_logo_candidates = [

        project_root
        / "exhibition-rooch-frontend"
        / "public"
        / "rooch-logo.png",

        project_root
        / "exhibition-rooch-frontend"
        / "public"
        / "rooch-logo.jpg",

        project_root
        / "exhibition-rooch-frontend"
        / "public"
        / "rooch-logo.jpeg",

        project_root
        / "exhibition-rooch-frontend"
        / "public"
        / "rooch-logo.webp",
    ]

    for path in frontend_logo_candidates:

        if path.is_file():
            return path

    fallback_candidates = [

        project_root / "logo.png",
        project_root / "logo.jpg",
        project_root / "logo.jpeg",
        project_root / "logo.webp",

        project_root
        / "exhibition-rooch-backend"
        / "logo.png",

        project_root
        / "exhibition-rooch-backend"
        / "assets"
        / "logo.png",

        project_root
        / "exhibition-rooch-backend"
        / "static"
        / "logo.png",

        Path.cwd() / "logo.png",
        Path.cwd() / "assets" / "logo.png",
        Path.cwd() / "static" / "logo.png",
    ]

    for path in fallback_candidates:

        if path.is_file():
            return path

    return None


# ============================================================
# ROOCH WORDMARK
# ============================================================

def _draw_logo(
    pdf: canvas.Canvas,
    x: float,
    top_y: float,
    max_width: float = 52 * mm,
    max_height: float = 24 * mm,
) -> float:
    """
    Draw only ROOCH.
    """

    pdf.setFillColor(
        ROOCH_MAROON
    )

    pdf.setFont(
        "Helvetica-Bold",
        21,
    )

    pdf.drawString(
        x,
        top_y - 7 * mm,
        "ROOCH",
    )

    pdf.setFillColor(
        ROOCH_TEXT
    )

    pdf.setFont(
        "Helvetica",
        7,
    )

    pdf.drawString(
        x,
        top_y - 11 * mm,
        "THE RADIANT YOU",
    )

    return top_y - 14 * mm


# ============================================================
# FOOTER
# ============================================================

def _draw_footer(
    pdf: canvas.Canvas,
) -> None:

    footer_y = 18 * mm

    pdf.setStrokeColor(
        ROOCH_BORDER
    )

    pdf.setLineWidth(
        0.6
    )

    pdf.line(
        20 * mm,
        footer_y + 5 * mm,
        PAGE_W - 20 * mm,
        footer_y + 5 * mm,
    )

    pdf.setFillColor(
        ROOCH_MUTED
    )

    pdf.setFont(
        "Helvetica",
        7.2,
    )

    pdf.drawCentredString(
        PAGE_W / 2,
        footer_y,
        "Thank you for shopping with ROOCH · This is a computer-generated invoice",
    )


# ============================================================
# PAGE BACKGROUND
# ============================================================

def _draw_page_background(
    pdf: canvas.Canvas,
) -> None:
    """
    Draw clean white invoice page.
    """

    pdf.setFillColor(
        ROOCH_WHITE
    )

    pdf.rect(
        0,
        0,
        PAGE_W,
        PAGE_H,
        fill=1,
        stroke=0,
    )


# ============================================================
# PRODUCT PHOTO
# ============================================================

def _draw_product_photo(
    pdf: canvas.Canvas,
    invoice: Invoice,
    y: float,
) -> float:
    """
    Draw product photo if available.

    The original image aspect ratio is preserved.

    No forced 1298 x 816 ratio.
    No cropping.
    No stretching.
    """

    photo_bottom = y

    if not invoice.product_photo_path:
        return photo_bottom

    try:

        local_path = None

        storage_backend = getattr(
            settings,
            "STORAGE_BACKEND",
            "local",
        )

        if storage_backend == "local":

            local_path = (
                storage
                .get_storage()
                .absolute_path(
                    invoice.product_photo_path
                )
            )

        if not (
            local_path
            and local_path.exists()
        ):
            return photo_bottom

        image = ImageReader(
            str(local_path)
        )

        image_width, image_height = (
            image.getSize()
        )

        if not (
            image_width > 0
            and image_height > 0
        ):
            return photo_bottom

        # ----------------------------------------------------
        # ORIGINAL IMAGE RATIO
        # ----------------------------------------------------

        max_width = 80 * mm
        max_height = 55 * mm

        scale = min(
            max_width / image_width,
            max_height / image_height,
        )

        width = (
            image_width
            * scale
        )

        height = (
            image_height
            * scale
        )

        image_x = (
            PAGE_W - width
        ) / 2

        image_y = (
            y - height
        )

        # ----------------------------------------------------
        # PHOTO BORDER
        # ----------------------------------------------------

        pdf.setStrokeColor(
            ROOCH_BORDER
        )

        pdf.setLineWidth(
            0.6
        )

        pdf.roundRect(
            image_x - 2 * mm,
            image_y - 2 * mm,
            width + 4 * mm,
            height + 4 * mm,
            1.5 * mm,
            fill=0,
            stroke=1,
        )

        # ----------------------------------------------------
        # PHOTO
        # ----------------------------------------------------

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
            image_y
            - 4 * mm
        )

    except Exception:

        photo_bottom = y

    return photo_bottom


# ============================================================
# LABEL HELPER
# ============================================================

def _draw_label(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    label: str,
    value: str | None = None,
    *,
    value_color=ROOCH_TEXT,
    label_color=ROOCH_MAROON,
    value_size: float = 8.5,
) -> float:

    pdf.setFillColor(
        label_color
    )

    pdf.setFont(
        "Helvetica-Bold",
        7,
    )

    pdf.drawString(
        x,
        y,
        label.upper(),
    )

    if value:

        value_y = (
            y
            - 4.8 * mm
        )

        pdf.setFillColor(
            value_color
        )

        pdf.setFont(
            "Helvetica-Bold",
            value_size,
        )

        pdf.drawString(
            x,
            value_y,
            value,
        )

        return value_y

    return y


# ============================================================
# PRODUCT TABLE HEADER
# ============================================================

def _draw_product_table_header(
    pdf: canvas.Canvas,
    left: float,
    right: float,
    y: float,
) -> float:
    """
    Draw product table header.

    Returns the Y position where the first product row
    should start.

    This function is also used when the table continues
    onto another page.
    """

    table_left = left
    table_right = right

    table_width = (
        table_right
        - table_left
    )

    # --------------------------------------------------------
    # COLUMN POSITIONS
    # --------------------------------------------------------

    col_product = (
        table_left
        + 4 * mm
    )

    col_item = (
        table_left
        + 78 * mm
    )

    col_qty = (
        table_left
        + 96 * mm
    )

    col_unit = (
        table_left
        + 135 * mm
    )

    col_amount = (
        table_right
        - 4 * mm
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    header_height = (
        8 * mm
    )

    pdf.setFillColor(
        ROOCH_IVORY
    )

    pdf.roundRect(
        table_left,
        y - header_height + 2 * mm,
        table_width,
        header_height,
        1.2 * mm,
        fill=1,
        stroke=0,
    )

    pdf.setFillColor(
        ROOCH_MAROON
    )

    pdf.setFont(
        "Helvetica-Bold",
        6.8,
    )

    header_y = (
        y
        - 2.5 * mm
    )

    pdf.drawString(
        col_product,
        header_y,
        "PRODUCT",
    )

    pdf.drawString(
        col_item,
        header_y,
        "ITEM",
    )

    pdf.drawString(
        col_qty,
        header_y,
        "QTY",
    )

    pdf.drawRightString(
        col_unit,
        header_y,
        "UNIT PRICE",
    )

    pdf.drawRightString(
        col_amount,
        header_y,
        "AMOUNT",
    )

    return (
        y
        - 9 * mm
    )


# ============================================================
# PDF GENERATION
# ============================================================

def build_invoice_pdf_bytes(
    invoice: Invoice,
) -> bytes:
    """
    Build complete Rooch invoice PDF.

    Important:
    When there are many items, the PDF automatically
    continues onto a new page instead of allowing
    GST / totals / footer content to overlap.
    """

    buffer = BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4,
    )

    left = 20 * mm

    right = (
        PAGE_W
        - 20 * mm
    )

    top = (
        PAGE_H
        - 18 * mm
    )

    # ========================================================
    # PAGE
    # ========================================================

    _draw_page_background(
        pdf
    )

    # ========================================================
    # HEADER
    # ========================================================

    logo_bottom = _draw_logo(
        pdf,
        left,
        top,
    )

    pdf.setFillColor(
        ROOCH_MAROON
    )

    pdf.setFont(
        "Helvetica-Bold",
        15,
    )

    pdf.drawRightString(
        right,
        top - 2 * mm,
        "TAX INVOICE",
    )

    pdf.setFillColor(
        ROOCH_TEXT
    )

    pdf.setFont(
        "Helvetica",
        7.5,
    )

    pdf.drawRightString(
        right,
        top - 8 * mm,
        f"Order: {invoice.invoice_number}",
    )

    created_at = getattr(
        invoice,
        "created_at",
        None,
    )

    pdf.drawRightString(
        right,
        top - 12 * mm,
        f"Date: {_format_date(created_at)}",
    )

    pdf.drawRightString(
        right,
        top - 16 * mm,
        "Status: DELIVERED",
    )

    # ========================================================
    # COMPANY DETAILS
    # ========================================================

    company_address = getattr(
        settings,
        "COMPANY_ADDRESS",
        None,
    )

    company_gstin = getattr(
        settings,
        "COMPANY_GSTIN",
        None,
    )

    company_email = getattr(
        settings,
        "COMPANY_EMAIL",
        None,
    )

    company_phone = getattr(
        settings,
        "COMPANY_PHONE",
        None,
    )

    company_y = (
        top
        - 16 * mm
    )

    if company_email:

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.drawString(
            left,
            company_y,
            str(company_email),
        )

        company_y -= (
            4 * mm
        )

    if company_phone:

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.drawString(
            left,
            company_y,
            str(company_phone),
        )

        company_y -= (
            4 * mm
        )

    if company_address:

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica",
            7.2,
        )

        for line in _wrapped_lines(
            str(company_address),
            75,
        ):

            pdf.drawString(
                left,
                company_y,
                line,
            )

            company_y -= (
                3.7 * mm
            )

    if company_gstin:

        pdf.setFillColor(
            ROOCH_TEXT
        )

        pdf.setFont(
            "Helvetica-Bold",
            7.5,
        )

        pdf.drawString(
            left,
            company_y,
            f"GSTIN: {company_gstin}",
        )

        company_y -= (
            4 * mm
        )

    # ========================================================
    # HEADER DIVIDER
    # ========================================================

    divider_y = (
        min(
            logo_bottom,
            company_y,
            top - 21 * mm,
        )
        - 5 * mm
    )

    pdf.setStrokeColor(
        ROOCH_GOLD_LIGHT
    )

    pdf.setLineWidth(
        0.7
    )

    pdf.line(
        left,
        divider_y,
        right,
        divider_y,
    )

    # ========================================================
    # BILL TO / SHIP TO
    # ========================================================

    section_top = (
        divider_y
        - 10 * mm
    )

    customer_name = str(
        invoice.customer_name
    )

    customer_phone = (
        str(invoice.customer_phone)
        if invoice.customer_phone
        else ""
    )

    customer_email = (
        str(invoice.customer_email)
        if invoice.customer_email
        else ""
    )

    # ========================================================
    # BILL TO
    # ========================================================

    bill_x = left

    _draw_label(
        pdf,
        bill_x,
        section_top,
        "BILL TO",
    )

    bill_y = (
        section_top
        - 5 * mm
    )

    pdf.setFillColor(
        ROOCH_TEXT
    )

    pdf.setFont(
        "Helvetica-Bold",
        9,
    )

    pdf.drawString(
        bill_x,
        bill_y,
        customer_name,
    )

    bill_y -= (
        4.5 * mm
    )

    pdf.setFillColor(
        ROOCH_MUTED
    )

    pdf.setFont(
        "Helvetica",
        7.5,
    )

    if customer_email:

        pdf.drawString(
            bill_x,
            bill_y,
            customer_email,
        )

        bill_y -= (
            3.8 * mm
        )

    if customer_phone:

        pdf.drawString(
            bill_x,
            bill_y,
            customer_phone,
        )

        bill_y -= (
            3.8 * mm
        )

    # ========================================================
    # SHIP TO
    # ========================================================

    ship_x = (
        left
        + 93 * mm
    )

    _draw_label(
        pdf,
        ship_x,
        section_top,
        "SHIP TO",
    )

    ship_y = (
        section_top
        - 5 * mm
    )

    # Hardcoded Exhibition.
    pdf.setFillColor(
        ROOCH_TEXT
    )

    pdf.setFont(
        "Helvetica-Bold",
        9,
    )

    pdf.drawString(
        ship_x,
        ship_y,
        "Exhibition",
    )

    ship_y -= (
        4.5 * mm
    )

    payment_text = _payment_text(
        invoice
    )

    if payment_text:

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.drawString(
            ship_x,
            ship_y,
            f"Payment: {payment_text}",
        )

        ship_y -= (
            3.8 * mm
        )

    y = (
        min(
            bill_y,
            ship_y,
        )
        - 8 * mm
    )

    # ========================================================
    # PRODUCT PHOTO
    # ========================================================

    if invoice.product_photo_path:

        photo_bottom = (
            _draw_product_photo(
                pdf,
                invoice,
                y,
            )
        )

        y = (
            photo_bottom
            - 7 * mm
        )

    # ========================================================
    # PRODUCTS TITLE
    # ========================================================

    pdf.setFillColor(
        ROOCH_TEXT
    )

    pdf.setFont(
        "Helvetica-Bold",
        10,
    )

    pdf.drawString(
        left,
        y,
        "PRODUCTS",
    )

    y -= (
        5 * mm
    )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    if invoice.product_description:

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica-Oblique",
            7.5,
        )

        for line in _wrapped_lines(
            invoice.product_description,
            100,
        ):

            pdf.drawString(
                left,
                y,
                line,
            )

            y -= (
                3.8 * mm
            )

        y -= (
            2 * mm
        )

    # ========================================================
    # TABLE HEADER
    # ========================================================

    y = _draw_product_table_header(
        pdf,
        left,
        right,
        y,
    )

    # ========================================================
    # PRODUCT TABLE COLUMN POSITIONS
    # ========================================================

    table_left = left
    table_right = right

    col_product = (
        table_left
        + 4 * mm
    )

    col_item = (
        table_left
        + 78 * mm
    )

    col_qty = (
        table_left
        + 96 * mm
    )

    col_unit = (
        table_left
        + 135 * mm
    )

    col_amount = (
        table_right
        - 4 * mm
    )

    # ========================================================
    # ITEMS
    # ========================================================

    items = list(
        invoice.items or []
    )

    for index, invoice_item in enumerate(
        items
    ):

        product_name = (
            invoice_item.product_name
            or "Item"
        )

        product_lines = _wrapped_lines(
            product_name,
            42,
        )

        # ----------------------------------------------------
        # ROW DIMENSIONS
        # ----------------------------------------------------

        line_height = (
            4.2 * mm
        )

        top_padding = (
            2.5 * mm
        )

        bottom_padding = (
            2.5 * mm
        )

        content_height = (
            len(product_lines)
            * line_height
        )

        row_height = max(
            10 * mm,
            content_height
            + top_padding
            + bottom_padding,
        )

        # ====================================================
        # PAGE BREAK FOR PRODUCT ROW
        # ====================================================
        #
        # This is the important fix.
        #
        # Before drawing a row, check whether the complete
        # row can fit above the footer.
        #
        # If not, start a new page.
        #
        # The row is NEVER split.
        # ====================================================

        if (
            y - row_height
            < CONTENT_BOTTOM_LIMIT
        ):

            # Finish current page.
            _draw_footer(
                pdf
            )

            pdf.showPage()

            # New page.
            _draw_page_background(
                pdf
            )

            # Start table again near the top.
            y = (
                PAGE_H
                - 25 * mm
            )

            # Small continuation title.
            pdf.setFillColor(
                ROOCH_MAROON
            )

            pdf.setFont(
                "Helvetica-Bold",
                9,
            )

            pdf.drawString(
                left,
                y,
                "PRODUCTS",
            )

            y -= (
                5 * mm
            )

            # Repeat table header.
            y = _draw_product_table_header(
                pdf,
                left,
                right,
                y,
            )

        # ====================================================
        # ROW BACKGROUND
        # ====================================================

        if index % 2 == 0:

            pdf.setFillColor(
                colors.HexColor(
                    "#FCFBF8"
                )
            )

            pdf.roundRect(
                table_left,
                y - row_height,
                table_right - table_left,
                row_height,
                0.8 * mm,
                fill=1,
                stroke=0,
            )

        # ====================================================
        # VERTICAL CENTERING
        # ====================================================

        content_total_height = (
            len(product_lines)
            * line_height
        )

        first_line_y = (
            y
            - (
                row_height
                - content_total_height
            )
            / 2
            - 0.8 * mm
        )

        row_y = first_line_y

        # ====================================================
        # PRODUCT CONTENT
        # ====================================================

        for line_index, product_line in enumerate(
            product_lines
        ):

            pdf.setFillColor(
                ROOCH_TEXT
            )

            pdf.setFont(
                "Helvetica",
                7.8,
            )

            pdf.drawString(
                col_product,
                row_y,
                product_line,
            )

            if line_index == 0:

                # ITEM
                pdf.setFillColor(
                    ROOCH_TEXT
                )

                pdf.setFont(
                    "Helvetica",
                    7.8,
                )

                pdf.drawString(
                    col_item,
                    row_y,
                    f"#{invoice_item.item_number}",
                )

                # QTY
                pdf.drawString(
                    col_qty,
                    row_y,
                    "1",
                )

                # UNIT PRICE
                pdf.setFont(
                    "Helvetica",
                    7.5,
                )

                pdf.drawRightString(
                    col_unit,
                    row_y,
                    f"Rs. {_money(invoice_item.unit_price)}",
                )

                # AMOUNT
                pdf.setFont(
                    "Helvetica-Bold",
                    7.5,
                )

                pdf.drawRightString(
                    col_amount,
                    row_y,
                    f"Rs. {_money(invoice_item.unit_price)}",
                )

            row_y -= line_height

        # ====================================================
        # ROW BOTTOM
        # ====================================================

        row_bottom = (
            y
            - row_height
        )

        # ----------------------------------------------------
        # SEPARATOR
        # ----------------------------------------------------

        separator_y = (
            row_bottom
            - 1.2 * mm
        )

        pdf.setStrokeColor(
            ROOCH_BORDER
        )

        pdf.setLineWidth(
            0.35
        )

        pdf.line(
            table_left,
            separator_y,
            table_right,
            separator_y,
        )

        # ----------------------------------------------------
        # NEXT ROW
        # ----------------------------------------------------

        y = (
            separator_y
            - 2.2 * mm
        )

    # ========================================================
    # TOTALS
    # ========================================================

    totals_left = (
        left
        + 105 * mm
    )

    totals_right = right

    # ========================================================
    # EXTRA TOP SPACE AFTER PRODUCTS
    # ========================================================

    y -= (
        3 * mm
    )

    # ========================================================
    # MONEY DRAW HELPER
    # ========================================================

    def draw_amount(
        x: float,
        y_pos: float,
        amount: Decimal | float | int | None,
        *,
        bold: bool = False,
        color=ROOCH_TEXT,
        size: float = 8.5,
    ) -> None:

        pdf.setFillColor(
            color
        )

        pdf.setFont(
            "Helvetica-Bold"
            if bold
            else "Helvetica",
            size,
        )

        pdf.drawRightString(
            x,
            y_pos,
            f"Rs. {_money(amount)}",
        )

    # ========================================================
    # TOTAL ITEMS
    # ========================================================

    total_items = len(items)

    pdf.setFillColor(
        ROOCH_TEXT
    )

    pdf.setFont(
        "Helvetica",
        8.5,
    )

    pdf.drawString(
        totals_left,
        y,
        "Total Items",
    )

    pdf.setFont(
        "Helvetica-Bold",
        8.5,
    )

    pdf.drawRightString(
        totals_right,
        y,
        str(total_items),
    )

    y -= (
        5 * mm
    )

    # ========================================================
    # SUBTOTAL
    # ========================================================

    pdf.setFillColor(
        ROOCH_TEXT
    )

    pdf.setFont(
        "Helvetica",
        8.5,
    )

    pdf.drawString(
        totals_left,
        y,
        "Subtotal",
    )

    draw_amount(
        totals_right,
        y,
        invoice.subtotal,
    )

    y -= (
        5 * mm
    )

    # ========================================================
    # DISCOUNT
    # ========================================================

    discount = (
        invoice.discount_amount
        or Decimal("0.00")
    )

    if discount > ZERO:

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica",
            8.5,
        )

        pdf.drawString(
            totals_left,
            y,
            "Discount",
        )

        pdf.setFillColor(
            ROOCH_MAROON
        )

        pdf.drawRightString(
            totals_right,
            y,
            f"- Rs. {_money(discount)}",
        )

        y -= (
            5 * mm
        )

    # ========================================================
    # GST DATA
    # ========================================================

    tax_percent = (
        invoice.tax_percent
        or Decimal("0.00")
    )

    taxable_value = (
        getattr(
            invoice,
            "taxable_value",
            None,
        )
        or ZERO
    )

    cgst_amount = (
        getattr(
            invoice,
            "cgst_amount",
            None,
        )
        or ZERO
    )

    sgst_amount = (
        getattr(
            invoice,
            "sgst_amount",
            None,
        )
        or ZERO
    )

    gst_amount = (
        getattr(
            invoice,
            "gst_amount",
            None,
        )
        or getattr(
            invoice,
            "tax_amount",
            None,
        )
        or (
            cgst_amount
            + sgst_amount
        )
    )

    cgst_rate = (
        getattr(
            invoice,
            "cgst_rate",
            None,
        )
        or (
            tax_percent
            / Decimal("2.00")
        )
    )

    sgst_rate = (
        getattr(
            invoice,
            "sgst_rate",
            None,
        )
        or (
            tax_percent
            / Decimal("2.00")
        )
    )

    # ========================================================
    # FINANCIAL SECTION PAGE SAFETY
    # ========================================================
    #
    # This is the second important fix.
    #
    # If GST + Grand Total cannot fit above the footer,
    # move the entire financial section to a new page.
    #
    # Therefore:
    #
    # PRODUCT TABLE
    #        ↓
    # TOTAL ITEMS
    #        ↓
    # SUBTOTAL
    #        ↓
    # DISCOUNT
    #        ↓
    # GST
    #        ↓
    # GRAND TOTAL
    #
    # will never overlap the footer.
    # ========================================================

    if (
        y
        < FINANCIAL_MIN_SPACE
    ):

        _draw_footer(
            pdf
        )

        pdf.showPage()

        _draw_page_background(
            pdf
        )

        y = (
            PAGE_H
            - 25 * mm
        )

        # Small financial continuation heading.
        pdf.setFillColor(
            ROOCH_MAROON
        )

        pdf.setFont(
            "Helvetica-Bold",
            9,
        )

        pdf.drawString(
            left,
            y,
            "INVOICE SUMMARY",
        )

        y -= (
            8 * mm
        )

    # ========================================================
    # GST BREAKUP
    # ========================================================

    if tax_percent > ZERO:

        gst_box_top = (
            y
            + 2 * mm
        )

        gst_box_height = (
            25 * mm
        )

        gst_box_bottom = (
            gst_box_top
            - gst_box_height
        )

        # ----------------------------------------------------
        # GST BOX
        # ----------------------------------------------------

        pdf.setFillColor(
            ROOCH_WHITE
        )

        pdf.setStrokeColor(
            ROOCH_BORDER
        )

        pdf.setLineWidth(
            0.6
        )

        pdf.roundRect(
            left,
            gst_box_bottom,
            right - left,
            gst_box_height,
            2 * mm,
            fill=1,
            stroke=1,
        )

        # ----------------------------------------------------
        # GST HEADING
        # ----------------------------------------------------

        heading_y = (
            gst_box_top
            - 6 * mm
        )

        pdf.setFillColor(
            ROOCH_MAROON
        )

        pdf.setFont(
            "Helvetica-Bold",
            8,
        )

        pdf.drawString(
            left + 5 * mm,
            heading_y,
            "GST BREAKUP",
        )

        pdf.setFillColor(
            ROOCH_TEXT
        )

        pdf.setFont(
            "Helvetica-Bold",
            6.8,
        )

        pdf.drawString(
            left + 37 * mm,
            heading_y,
            "(INCLUSIVE IN PRODUCT PRICE)",
        )

        # ----------------------------------------------------
        # GST COLUMNS
        # ----------------------------------------------------

        gst_label_y = (
            gst_box_top
            - 12 * mm
        )

        gst_value_y = (
            gst_box_bottom
            + 5.5 * mm
        )

        gst_col_1 = (
            left + 5 * mm
        )

        gst_col_2 = (
            left + 61 * mm
        )

        gst_col_3 = (
            left + 116 * mm
        )

        gst_col_4 = (
            right - 5 * mm
        )

        # ----------------------------------------------------
        # GST LABELS
        # ----------------------------------------------------

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica",
            7,
        )

        pdf.drawString(
            gst_col_1,
            gst_label_y,
            "Taxable Value",
        )

        pdf.drawString(
            gst_col_2,
            gst_label_y,
            f"CGST @{_money(cgst_rate)}%",
        )

        pdf.drawString(
            gst_col_3,
            gst_label_y,
            f"SGST @{_money(sgst_rate)}%",
        )

        pdf.drawRightString(
            gst_col_4,
            gst_label_y,
            "Total GST",
        )

        # ----------------------------------------------------
        # GST VALUES
        # ----------------------------------------------------

        pdf.setFont(
            "Helvetica-Bold",
            8.8,
        )

        pdf.setFillColor(
            ROOCH_TEXT
        )

        pdf.drawString(
            gst_col_1,
            gst_value_y,
            f"Rs. {_money(taxable_value)}",
        )

        pdf.drawString(
            gst_col_2,
            gst_value_y,
            f"Rs. {_money(cgst_amount)}",
        )

        pdf.drawString(
            gst_col_3,
            gst_value_y,
            f"Rs. {_money(sgst_amount)}",
        )

        pdf.setFillColor(
            ROOCH_MAROON
        )

        pdf.drawRightString(
            gst_col_4,
            gst_value_y,
            f"Rs. {_money(gst_amount)}",
        )

        y = (
            gst_box_bottom
            - 8 * mm
        )

    # ========================================================
    # GRAND TOTAL
    # ========================================================

    grand_total = (
        getattr(
            invoice,
            "grand_total",
            None,
        )
        or getattr(
            invoice,
            "total",
            None,
        )
        or (
            invoice.subtotal
            - discount
        )
    )

    grand_total = Decimal(
        str(grand_total)
    ).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )

    # ========================================================
    # GRAND TOTAL LINE
    # ========================================================

    pdf.setStrokeColor(
        ROOCH_TEXT
    )

    pdf.setLineWidth(
        0.8
    )

    pdf.line(
        totals_left,
        y + 3 * mm,
        totals_right,
        y + 3 * mm,
    )

    # ========================================================
    # GRAND TOTAL
    # ========================================================

    pdf.setFillColor(
        ROOCH_MAROON
    )

    pdf.setFont(
        "Helvetica-Bold",
        10,
    )

    pdf.drawString(
        totals_left,
        y - 2 * mm,
        "Total Payable",
    )

    pdf.setFillColor(
        ROOCH_MAROON
    )

    pdf.setFont(
        "Helvetica-Bold",
        12,
    )

    pdf.drawRightString(
        totals_right,
        y - 2 * mm,
        f"Rs. {_money(grand_total)}",
    )

    y -= (
        12 * mm
    )

    # ========================================================
    # NOTES
    # ========================================================

    if invoice.notes:

        # If notes cannot fit safely, start a new page.
        if (
            y
            < CONTENT_BOTTOM_LIMIT + 20 * mm
        ):

            _draw_footer(
                pdf
            )

            pdf.showPage()

            _draw_page_background(
                pdf
            )

            y = (
                PAGE_H
                - 25 * mm
            )

        y -= (
            5 * mm
        )

        pdf.setFillColor(
            ROOCH_MAROON
        )

        pdf.setFont(
            "Helvetica-Bold",
            8,
        )

        pdf.drawString(
            left,
            y,
            "NOTES",
        )

        y -= (
            4.5 * mm
        )

        pdf.setFillColor(
            ROOCH_MUTED
        )

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        for line in _wrapped_lines(
            invoice.notes,
            100,
        ):

            pdf.drawString(
                left,
                y,
                line,
            )

            y -= (
                4 * mm
            )

    # ========================================================
    # FOOTER
    # ========================================================

    _draw_footer(
        pdf
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
    Generate invoice PDF and save through configured storage.
    """

    pdf_bytes = (
        build_invoice_pdf_bytes(
            invoice
        )
    )

    if not pdf_bytes:

        raise ValueError(
            "Invoice PDF generation returned empty data."
        )

    filename = (
        f"{invoice.invoice_number}.pdf"
    )

    return storage.save_bytes(
        pdf_bytes,
        "invoices",
        filename,
    )