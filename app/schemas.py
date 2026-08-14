"""
Pydantic schemas for the Rooch exhibition invoice application.

Supports:

- Agent authentication
- Multiple individually priced invoice items
- Optional customer phone/email
- Cash / Online payment mode
- GST-inclusive pricing
- GST enabled / disabled
- GST breakup
- Discount
- Persisted grand total
- Product photo
- Offline synchronization using client_uuid
- WhatsApp / SMS delivery logs
"""

from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


# ============================================================
# ENUMS
# ============================================================


class PaymentMode(
    str,
    Enum,
):
    """
    Payment method selected for the invoice.
    """

    online = "online"
    cash = "cash"


# ============================================================
# AGENT / AUTH
# ============================================================


class AgentCreate(BaseModel):
    """
    Create a booth agent account.
    """

    full_name: str = Field(
        ...,
        min_length=1,
        max_length=120,
    )

    email: EmailStr

    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
    )

    role: str = Field(
        default="agent",
        max_length=20,
    )

    booth_name: str | None = Field(
        default=None,
        max_length=120,
    )

    @field_validator("full_name")
    @classmethod
    def validate_full_name(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Full name is required."
            )

        return value


class AgentOut(BaseModel):
    """
    Public agent information.

    Password hashes are never exposed.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    full_name: str

    email: str

    role: str

    booth_name: str | None = None


class LoginRequest(BaseModel):
    """
    Agent login request.
    """

    email: EmailStr

    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
    )


class TokenResponse(BaseModel):
    """
    Authentication response.
    """

    access_token: str

    token_type: str = "bearer"

    agent: AgentOut | None = None


# ============================================================
# MESSAGE LOG
# ============================================================


class MessageLogOut(BaseModel):
    """
    WhatsApp / SMS delivery attempt.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    channel: str

    status: str

    provider_sid: str | None = None

    error_message: str | None = None

    created_at: datetime


# ============================================================
# INVOICE ITEM INPUT
# ============================================================


class InvoiceItemCreate(BaseModel):
    """
    One individually priced product.

    Example:

        Rings #1 -> ₹250
        Rings #2 -> ₹400
        Necklace #1 -> ₹600
    """

    product_name: str | None = Field(
        default=None,
        max_length=200,
    )

    item_number: int = Field(
        ...,
        ge=1,
        le=5,
    )

    unit_price: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
    )

    @field_validator("product_name")
    @classmethod
    def validate_product_name(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            return None

        value = value.strip()

        return value or None


# ============================================================
# INVOICE ITEM OUTPUT
# ============================================================


class InvoiceItemOut(BaseModel):
    """
    Individually priced invoice item returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    product_name: str | None

    item_number: int

    unit_price: Decimal


# ============================================================
# INVOICE CREATE
# ============================================================


class InvoiceCreate(BaseModel):
    """
    Data used to create an invoice.

    Item prices are final customer-facing prices.

    GST is included inside those prices.

    The backend calculates the final grand total.
    """

    # --------------------------------------------------------
    # IDEMPOTENCY
    # --------------------------------------------------------

    client_uuid: str = Field(
        ...,
        min_length=1,
        max_length=36,
    )

    # --------------------------------------------------------
    # CUSTOMER
    # --------------------------------------------------------

    customer_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    customer_phone: str | None = Field(
        default=None,
        max_length=20,
    )

    customer_email: str | None = Field(
        default=None,
        max_length=255,
    )

    # --------------------------------------------------------
    # PRODUCTS
    # --------------------------------------------------------

    items: list[InvoiceItemCreate] = Field(
        ...,
        min_length=1,
    )

    product_description: str | None = None

    # --------------------------------------------------------
    # GST
    # --------------------------------------------------------

    gst_enabled: bool = Field(
        default=False,
    )

    tax_percent: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
        max_digits=5,
        decimal_places=2,
    )

    # --------------------------------------------------------
    # DISCOUNT
    # --------------------------------------------------------

    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
    )

    # --------------------------------------------------------
    # PAYMENT
    # --------------------------------------------------------

    payment_mode: PaymentMode = Field(
        default=PaymentMode.online,
    )

    # --------------------------------------------------------
    # OTHER
    # --------------------------------------------------------

    notes: str | None = None

    exhibition_name: str | None = Field(
        default=None,
        max_length=200,
    )

    captured_at: datetime | None = None

    # --------------------------------------------------------
    # VALIDATORS
    # --------------------------------------------------------

    @field_validator("client_uuid")
    @classmethod
    def validate_client_uuid(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "client_uuid is required."
            )

        return value

    @field_validator("customer_name")
    @classmethod
    def validate_customer_name(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Customer name is required."
            )

        return value

    @field_validator("customer_phone")
    @classmethod
    def normalize_phone(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("customer_email")
    @classmethod
    def normalize_email(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("product_description")
    @classmethod
    def normalize_product_description(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("notes")
    @classmethod
    def normalize_notes(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("exhibition_name")
    @classmethod
    def normalize_exhibition_name(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            return None

        value = value.strip()

        return value or None


# ============================================================
# OFFLINE PHOTO DATA
# ============================================================


class OfflinePhotoFields(BaseModel):
    """
    Product photo stored locally in IndexedDB.

    These fields are used ONLY during offline synchronization.

    photo_base64 contains the raw Base64 image data.

    photo_content_type contains the MIME type, for example:

        image/jpeg
        image/png
        image/webp
        image/heic
    """

    photo_base64: str = Field(
        ...,
        min_length=1,
    )

    photo_content_type: str = Field(
        default="image/jpeg",
        min_length=1,
        max_length=100,
    )

    @field_validator("photo_base64")
    @classmethod
    def validate_photo_base64(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Product photo is required."
            )

        return value

    @field_validator("photo_content_type")
    @classmethod
    def normalize_photo_content_type(
        cls,
        value: str,
    ) -> str:

        value = value.strip().lower()

        if not value:
            return "image/jpeg"

        return value


# ============================================================
# GST BREAKUP
# ============================================================


class GSTBreakup(BaseModel):
    """
    GST breakup for GST-inclusive pricing.
    """

    gst_enabled: bool = False

    gst_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=5,
        decimal_places=2,
    )

    taxable_value: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
    )

    gst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
    )

    cgst_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=5,
        decimal_places=2,
    )

    cgst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
    )

    sgst_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=5,
        decimal_places=2,
    )

    sgst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
    )

    inclusive: bool = True


# ============================================================
# INVOICE OUTPUT
# ============================================================


class InvoiceOut(BaseModel):
    """
    Complete invoice returned by the backend.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    client_uuid: str

    invoice_number: str

    customer_name: str

    customer_phone: str | None = None

    customer_email: str | None = None

    product_description: str | None = None

    items: list[InvoiceItemOut] = Field(
        default_factory=list,
    )

    # --------------------------------------------------------
    # GST
    # --------------------------------------------------------

    gst_enabled: bool = False

    tax_percent: Decimal = Decimal(
        "0.00"
    )

    tax_amount: Decimal = Decimal(
        "0.00"
    )

    gst_breakup: GSTBreakup = Field(
        default_factory=GSTBreakup,
    )

    # --------------------------------------------------------
    # DISCOUNT
    # --------------------------------------------------------

    discount_amount: Decimal = Decimal(
        "0.00"
    )

    # --------------------------------------------------------
    # PAYMENT
    # --------------------------------------------------------

    payment_mode: PaymentMode = (
        PaymentMode.online
    )

    # --------------------------------------------------------
    # CALCULATED TOTALS
    # --------------------------------------------------------

    quantity: int = 0

    subtotal: Decimal = Decimal(
        "0.00"
    )

    total: Decimal = Decimal(
        "0.00"
    )

    grand_total: Decimal = Decimal(
        "0.00"
    )

    # --------------------------------------------------------
    # ADDITIONAL
    # --------------------------------------------------------

    notes: str | None = None

    exhibition_name: str | None = None

    product_photo_path: str | None = None

    pdf_path: str | None = None

    created_at: datetime

    captured_at: datetime

    messages: list[MessageLogOut] = Field(
        default_factory=list,
    )


# ============================================================
# INVOICE LIST
# ============================================================


class InvoiceListItem(BaseModel):
    """
    Lightweight invoice representation.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    invoice_number: str

    customer_name: str

    customer_phone: str | None = None

    total: Decimal = Decimal(
        "0.00"
    )

    grand_total: Decimal = Decimal(
        "0.00"
    )

    created_at: datetime

    quantity: int = 0

    payment_mode: PaymentMode = (
        PaymentMode.online
    )


# ============================================================
# RESEND
# ============================================================


class ResendRequest(BaseModel):
    """
    Optional resend payload.
    """

    force: bool = False


# ============================================================
# OFFLINE SYNC ITEM
# ============================================================


class InvoiceSyncItem(
    InvoiceCreate,
    OfflinePhotoFields,
):
    """
    Invoice received from IndexedDB.

    This is the IMPORTANT FIX.

    An offline invoice contains everything from InvoiceCreate
    PLUS:

        photo_base64
        photo_content_type

    This allows sync.py to receive the offline product photo
    instead of losing it during Pydantic validation.
    """



# ============================================================
# OFFLINE SYNC REQUEST
# ============================================================


class InvoiceSyncRequest(BaseModel):
    """
    Batch of invoices waiting for synchronization.
    """

    items: list[InvoiceSyncItem] = Field(
        default_factory=list,
    )


# ============================================================
# BACKWARD-COMPATIBLE SYNC REQUEST NAME
# ============================================================


SyncRequest = InvoiceSyncRequest


# ============================================================
# SYNC RESULT
# ============================================================


class SyncResultItem(BaseModel):
    """
    Result for one synchronized invoice.
    """

    client_uuid: str

    status: str

    invoice_id: int | None = None

    invoice_number: str | None = None

    error: str | None = None


# ============================================================
# SYNC RESPONSE
# ============================================================


class InvoiceSyncResponse(BaseModel):
    """
    Batch synchronization response.
    """

    results: list[SyncResultItem]


# ============================================================
# BACKWARD-COMPATIBLE SYNC RESPONSE NAME
# ============================================================


SyncResponse = InvoiceSyncResponse


# ============================================================
# GENERIC MESSAGE
# ============================================================


class MessageResponse(BaseModel):
    """
    Generic API message.
    """

    message: str


# ============================================================
# INVOICE TOTALS
# ============================================================


class InvoiceTotals(BaseModel):
    """
    Lightweight totals object useful for PDF generation
    and frontend summary calculations.
    """

    subtotal: Decimal = Decimal(
        "0.00"
    )

    taxable_value: Decimal = Decimal(
        "0.00"
    )

    gst_amount: Decimal = Decimal(
        "0.00"
    )

    cgst_amount: Decimal = Decimal(
        "0.00"
    )

    sgst_amount: Decimal = Decimal(
        "0.00"
    )

    discount_amount: Decimal = Decimal(
        "0.00"
    )

    total: Decimal = Decimal(
        "0.00"
    )

    grand_total: Decimal = Decimal(
        "0.00"
    )

    payment_mode: PaymentMode = (
        PaymentMode.online
    )