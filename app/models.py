"""SQLAlchemy ORM models."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

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


# ============================================================
# ENUMS
# ============================================================


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


# ============================================================
# AGENT
# ============================================================


class Agent(Base):
    """
    A sales/booth staff account that logs into the app.
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    full_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[AgentRole] = mapped_column(
        Enum(AgentRole),
        default=AgentRole.agent,
        nullable=False,
    )

    booth_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="agent",
    )


# ============================================================
# INVOICE
# ============================================================


class Invoice(Base):
    """
    One invoice represents one customer visit.

    An invoice can contain multiple individually priced items.

    Example:

        Rings #1      ₹250
        Rings #2      ₹400
        Necklace #1   ₹600
        Bracelet #1   ₹300
        Bracelet #2   ₹400

    client_uuid is generated on the device and is used as an
    idempotency key when syncing offline invoices.
    """

    __tablename__ = "invoices"

    __table_args__ = (
        UniqueConstraint(
            "client_uuid",
            name="uq_invoice_client_uuid",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    client_uuid: Mapped[str] = mapped_column(
        String(36),
        default=_uuid,
        index=True,
        nullable=False,
    )

    invoice_number: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
    )

    # --------------------------------------------------------
    # Agent
    # --------------------------------------------------------

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id"),
        nullable=False,
    )

    agent: Mapped["Agent"] = relationship(
        back_populates="invoices",
    )

    # --------------------------------------------------------
    # Customer details
    # --------------------------------------------------------

    customer_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # Phone is OPTIONAL according to the new frontend requirement.
    customer_phone: Mapped[str | None] = mapped_column(
        String(20),
        index=True,
        nullable=True,
    )

    # Email is also OPTIONAL.
    customer_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # --------------------------------------------------------
    # General invoice/product information
    # --------------------------------------------------------

    product_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tax_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    exhibition_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # --------------------------------------------------------
    # Files
    # --------------------------------------------------------

    # The actual API will enforce that a photo is supplied.
    # Keeping the database column nullable allows the invoice
    # record to be created/processed safely during the request.
    product_photo_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    pdf_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # --------------------------------------------------------
    # Timestamps
    # --------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.id",
    )

    messages: Mapped[list["MessageLog"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )

    # --------------------------------------------------------
    # Calculated values
    # --------------------------------------------------------

    @property
    def subtotal(self) -> Decimal:
        """
        Sum of all manually entered item prices.

        Example:
            Rings #1      250
            Rings #2      400
            Bracelet #1  300

        subtotal = 950
        """

        return sum(
            (item.unit_price for item in self.items),
            Decimal("0.00"),
        )

    @property
    def quantity(self) -> int:
        """
        Total number of individually priced items.

        Quantity is derived from the number of invoice items
        instead of being manually stored.

        Example:
            Rings #1
            Rings #2
            Bracelet #1

        quantity = 3
        """

        return len(self.items)

    @property
    def tax_amount(self) -> Decimal:
        """
        Calculate tax from the invoice subtotal.
        """

        amount = (
            self.subtotal
            * self.tax_percent
            / Decimal("100")
        )

        return amount.quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        """
        Final invoice total.

        total = subtotal + tax - discount
        """

        total = (
            self.subtotal
            + self.tax_amount
            - self.discount_amount
        )

        return max(
            Decimal("0.00"),
            total.quantize(Decimal("0.01")),
        )


# ============================================================
# INVOICE ITEM
# ============================================================


class InvoiceItem(Base):
    """
    One individually priced item inside an invoice.

    There is intentionally NO fixed product price.

    Example:

        Invoice 101

        Rings      #1    ₹250
        Rings      #2    ₹400
        Bracelet   #1    ₹300
        Bracelet   #2    ₹450

    Another invoice can have completely different prices.

    item_number represents the UI position:

        1 | 2 | 3 | 4 | 5
    """

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=False,
        index=True,
    )

    invoice: Mapped["Invoice"] = relationship(
        back_populates="items",
    )

    product_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    item_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )


# ============================================================
# MESSAGE LOG
# ============================================================


class MessageLog(Base):
    """
    Record of every WhatsApp/SMS send attempt for an invoice.
    """

    __tablename__ = "message_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=False,
    )

    invoice: Mapped["Invoice"] = relationship(
        back_populates="messages",
    )

    channel: Mapped[MessageChannel] = mapped_column(
        Enum(MessageChannel),
        nullable=False,
    )

    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus),
        default=MessageStatus.pending,
        nullable=False,
    )

    provider_sid: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )