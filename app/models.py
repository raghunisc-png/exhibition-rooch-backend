"""SQLAlchemy ORM models."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AgentRole(str, enum.Enum):
    admin = "admin"
    agent = "agent"


class MessageChannel(str, enum.Enum):
    whatsapp = "whatsapp"
    sms = "sms"


class MessageStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class Agent(Base):
    """A sales/booth staff account that logs into the app."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AgentRole] = mapped_column(Enum(AgentRole), default=AgentRole.agent)
    booth_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="agent")


class Invoice(Base):
    """
    One invoice = one customer visit capturing a product they bought at the
    exhibition booth. client_uuid is generated on the device at creation time
    (works offline) and used as an idempotency key when syncing, so retries
    / duplicate submits never create duplicate invoices.
    """

    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("client_uuid", name="uq_invoice_client_uuid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_uuid: Mapped[str] = mapped_column(String(36), default=_uuid, index=True)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)

    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    agent: Mapped["Agent"] = relationship(back_populates="invoices")

    # Customer details
    customer_name: Mapped[str] = mapped_column(String(150))
    customer_phone: Mapped[str] = mapped_column(String(20), index=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Product details
    product_name: Mapped[str] = mapped_column(String(200))
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product_photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    exhibition_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    # Timestamp on the device when it was originally captured (may be earlier
    # than created_at if the invoice was created offline and synced later).
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    messages: Mapped[list["MessageLog"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")

    @property
    def subtotal(self) -> float:
        return float(self.unit_price) * self.quantity

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * float(self.tax_percent) / 100, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax_amount - float(self.discount_amount), 2)


class MessageLog(Base):
    """Record of every WhatsApp/SMS send attempt for an invoice."""

    __tablename__ = "message_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    invoice: Mapped["Invoice"] = relationship(back_populates="messages")

    channel: Mapped[MessageChannel] = mapped_column(Enum(MessageChannel))
    status: Mapped[MessageStatus] = mapped_column(Enum(MessageStatus), default=MessageStatus.pending)
    provider_sid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
