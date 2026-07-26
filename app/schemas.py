"""Pydantic request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import AgentRole, MessageChannel, MessageStatus


# ---------- Auth ----------
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


# ---------- Invoices ----------
PHONE_REGEX_HINT = "Use E.164 format, e.g. +919876543210"


class InvoiceBase(BaseModel):
    client_uuid: str = Field(description="Client-generated UUID, used for offline idempotency")
    customer_name: str = Field(min_length=1, max_length=150)
    customer_phone: str = Field(min_length=8, max_length=20)
    customer_email: EmailStr | None = None
    product_name: str = Field(min_length=1, max_length=200)
    product_description: str | None = None
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(default=0, ge=0)
    tax_percent: float = Field(default=0, ge=0, le=100)
    discount_amount: float = Field(default=0, ge=0)
    notes: str | None = None
    exhibition_name: str | None = None
    captured_at: datetime | None = None

    @field_validator("customer_phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "")
        if not v.startswith("+"):
            raise ValueError(f"Phone number must include country code and start with '+'. {PHONE_REGEX_HINT}")
        if not v[1:].isdigit():
            raise ValueError(f"Phone number must contain only digits after '+'. {PHONE_REGEX_HINT}")
        return v


class InvoiceCreate(InvoiceBase):
    """Used for the multipart/form-data create endpoint (photo attached separately)."""
    pass


class MessageLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    channel: MessageChannel
    status: MessageStatus
    error_message: str | None = None
    created_at: datetime


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_uuid: str
    invoice_number: str
    customer_name: str
    customer_phone: str
    customer_email: EmailStr | None = None
    product_name: str
    product_description: str | None = None
    quantity: int
    unit_price: float
    tax_percent: float
    discount_amount: float
    notes: str | None = None
    exhibition_name: str | None = None
    product_photo_path: str | None = None
    pdf_path: str | None = None
    created_at: datetime
    captured_at: datetime
    subtotal: float
    tax_amount: float
    total: float
    messages: list[MessageLogOut] = []


class InvoiceListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_number: str
    customer_name: str
    customer_phone: str
    product_name: str
    total: float
    created_at: datetime


class SyncInvoiceItem(InvoiceBase):
    """
    An invoice captured while offline. Photos are base64-encoded since the
    whole batch travels as one JSON payload once connectivity returns.
    """
    photo_base64: str | None = None
    photo_content_type: str | None = None


class SyncRequest(BaseModel):
    items: list[SyncInvoiceItem]


class SyncResultItem(BaseModel):
    client_uuid: str
    status: str  # "created" | "duplicate" | "error"
    invoice_id: int | None = None
    invoice_number: str | None = None
    error: str | None = None


class SyncResponse(BaseModel):
    results: list[SyncResultItem]


class ResendRequest(BaseModel):
    channel: MessageChannel | None = None  # None = try whatsapp then sms
