"""Pydantic request/response schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.models import (
    AgentRole,
    MessageChannel,
    MessageStatus,
)


# ============================================================
# AUTH
# ============================================================


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    agent: "AgentOut"


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: AgentRole
    booth_name: str | None = None


class AgentCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    booth_name: str | None = None
    role: AgentRole = AgentRole.agent


# ============================================================
# PHONE VALIDATION
# ============================================================


PHONE_REGEX_HINT = (
    "Use E.164 format, e.g. +919876543210"
)


def normalize_optional_phone(
    value: str | None,
) -> str | None:
    """
    Normalize an optional phone number.

    Empty values are allowed because phone is optional.

    If supplied, the number must:
      - start with +
      - contain digits after +
      - contain 8-15 digits
    """

    if value is None:
        return None

    value = (
        value
        .strip()
        .replace(" ", "")
        .replace("-", "")
    )

    if not value:
        return None

    if not value.startswith("+"):
        raise ValueError(
            "Phone number must include country code "
            f"and start with '+'. {PHONE_REGEX_HINT}"
        )

    if not value[1:].isdigit():
        raise ValueError(
            "Phone number must contain only digits "
            f"after '+'. {PHONE_REGEX_HINT}"
        )

    if not 8 <= len(value[1:]) <= 15:
        raise ValueError(
            PHONE_REGEX_HINT
        )

    return value


# ============================================================
# INVOICE ITEM
# ============================================================


class InvoiceItemCreate(BaseModel):
    """
    One individually priced product/item.

    Example:

        {
            "product_name": "Rings",
            "item_number": 1,
            "unit_price": 250
        }

    The price is manually entered by the booth user.
    There is NO fixed price for a product.
    """

    product_name: str = Field(
        min_length=1,
        max_length=200,
    )

    item_number: int = Field(
        ge=1,
        le=5,
        description=(
            "UI position of the item. "
            "The current frontend supports positions 1-5."
        ),
    )

    unit_price: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    @field_validator("product_name")
    @classmethod
    def validate_product_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Product name is required."
            )

        return value


# ============================================================
# INVOICE CREATE
# ============================================================


class InvoiceBase(BaseModel):
    """
    Common invoice fields.

    Important:
      - customer_name is required
      - customer_phone is optional
      - customer_email is optional
      - items contains the individually priced products
      - product photo is required by the API endpoint
    """

    client_uuid: str = Field(
        description=(
            "Client-generated UUID used for "
            "offline idempotency."
        )
    )

    customer_name: str = Field(
        min_length=1,
        max_length=150,
    )

    customer_phone: str | None = Field(
        default=None,
        max_length=20,
    )

    customer_email: EmailStr | None = None

    items: list[InvoiceItemCreate] = Field(
        min_length=1,
        description=(
            "At least one manually priced product item "
            "must be supplied."
        ),
    )

    product_description: str | None = None

    tax_percent: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )

    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    notes: str | None = None

    exhibition_name: str | None = None

    captured_at: datetime | None = None

    # --------------------------------------------------------
    # Validators
    # --------------------------------------------------------

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
        return normalize_optional_phone(value)

    @field_validator("items")
    @classmethod
    def validate_items(
        cls,
        items: list[InvoiceItemCreate],
    ) -> list[InvoiceItemCreate]:
        if not items:
            raise ValueError(
                "At least one product item is required."
            )

        return items


class InvoiceCreate(InvoiceBase):
    """
    Used for the multipart/form-data create endpoint.

    The product photo is attached separately as an UploadFile.

    The router will enforce that the photo is mandatory.
    """

    pass


# ============================================================
# INVOICE ITEM RESPONSE
# ============================================================


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    product_name: str
    item_number: int
    unit_price: Decimal


# ============================================================
# MESSAGE LOG RESPONSE
# ============================================================


class MessageLogOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    channel: MessageChannel
    status: MessageStatus
    error_message: str | None = None
    created_at: datetime


# ============================================================
# INVOICE RESPONSE
# ============================================================


class InvoiceOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    client_uuid: str

    invoice_number: str

    customer_name: str

    customer_phone: str | None = None

    customer_email: EmailStr | None = None

    product_description: str | None = None

    items: list[InvoiceItemOut]

    tax_percent: Decimal

    discount_amount: Decimal

    notes: str | None = None

    exhibition_name: str | None = None

    product_photo_path: str | None = None

    pdf_path: str | None = None

    created_at: datetime

    captured_at: datetime

    # Calculated by SQLAlchemy properties.
    quantity: int

    subtotal: Decimal

    tax_amount: Decimal

    total: Decimal

    messages: list[MessageLogOut] = []


# ============================================================
# INVOICE LIST RESPONSE
# ============================================================


class InvoiceListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    invoice_number: str

    customer_name: str

    customer_phone: str | None = None

    total: Decimal

    created_at: datetime

    quantity: int


# ============================================================
# OFFLINE SYNC
# ============================================================


class SyncInvoiceItem(InvoiceBase):
    """
    An invoice captured while offline.

    The frontend stores the product photo as base64 because
    the entire pending invoice can later be synchronized
    as one JSON request.

    Product photo is REQUIRED for an offline invoice too.
    """

    photo_base64: str = Field(
        min_length=1,
        description=(
            "Base64 encoded product photo. "
            "Required because product photo is mandatory."
        ),
    )

    photo_content_type: str = Field(
        min_length=1,
        max_length=100,
    )


class SyncRequest(BaseModel):
    items: list[SyncInvoiceItem] = Field(
        min_length=1,
    )


class SyncResultItem(BaseModel):
    client_uuid: str

    # "created" | "duplicate" | "error"
    status: str

    invoice_id: int | None = None

    invoice_number: str | None = None

    error: str | None = None


class SyncResponse(BaseModel):
    results: list[SyncResultItem]


# ============================================================
# RESEND MESSAGE
# ============================================================


class ResendRequest(BaseModel):
    """
    If channel is None, the backend can attempt WhatsApp
    first and then SMS according to the messaging service.
    """

    channel: MessageChannel | None = None