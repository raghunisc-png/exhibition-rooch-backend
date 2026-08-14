"""
SQLAlchemy ORM models.

Invoice system supports:

- Multiple individually priced products
- Optional customer phone/email
- Online / Cash payment mode
- GST inclusive in displayed product prices
- GST enabled/disabled per invoice
- GST rate
- CGST / SGST breakup
- Discount
- Persisted grand total
- Product photo
- Generated PDF
- Offline synchronization through client_uuid
"""

from __future__ import annotations

import enum
import uuid

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

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

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database import Base


# ============================================================
# HELPERS
# ============================================================


def _uuid() -> str:
    """
    Generate a UUID string for invoice idempotency.
    """

    return str(
        uuid.uuid4()
    )


MONEY_QUANT = Decimal("0.01")


def _money(
    value: Decimal | None,
) -> Decimal:
    """
    Normalize a monetary Decimal value to two decimal places.
    """

    if value is None:
        value = Decimal("0.00")

    return Decimal(
        value
    ).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# ENUMS
# ============================================================


class AgentRole(
    str,
    enum.Enum,
):
    admin = "admin"
    agent = "agent"


class MessageChannel(
    str,
    enum.Enum,
):
    whatsapp = "whatsapp"
    sms = "sms"


class MessageStatus(
    str,
    enum.Enum,
):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class PaymentMode(
    str,
    enum.Enum,
):
    """
    Payment method selected for the invoice.

    Canonical values:

        online
        cash
    """

    online = "online"
    cash = "cash"

    def __str__(self) -> str:
        """
        Return the actual enum value.

        Example:

            str(PaymentMode.online)

        returns:

            online
        """

        return self.value


# ============================================================
# AGENT
# ============================================================


class Agent(Base):
    """
    A sales / booth staff account that logs into the app.
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
        Enum(
            AgentRole,
            name="agent_role",
        ),
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

    Product prices are final customer-facing prices.

    Product prices already include GST when GST is enabled.

    client_uuid is the device-generated idempotency key used
    when synchronizing offline invoices.
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

    # --------------------------------------------------------
    # OFFLINE / IDEMPOTENCY
    # --------------------------------------------------------

    client_uuid: Mapped[str] = mapped_column(
        String(36),
        default=_uuid,
        index=True,
        nullable=False,
    )

    # --------------------------------------------------------
    # INVOICE NUMBER
    # --------------------------------------------------------

    invoice_number: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
    )

    # --------------------------------------------------------
    # AGENT
    # --------------------------------------------------------

    agent_id: Mapped[int] = mapped_column(
        ForeignKey(
            "agents.id"
        ),
        nullable=False,
    )

    agent: Mapped["Agent"] = relationship(
        back_populates="invoices",
    )

    # --------------------------------------------------------
    # CUSTOMER
    # --------------------------------------------------------

    customer_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    customer_phone: Mapped[str | None] = mapped_column(
        String(20),
        index=True,
        nullable=True,
    )

    customer_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # --------------------------------------------------------
    # GENERAL INVOICE INFORMATION
    # --------------------------------------------------------

    product_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ========================================================
    # GST
    # ========================================================

    gst_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    tax_percent: Mapped[Decimal] = mapped_column(
        Numeric(
            5,
            2,
        ),
        default=Decimal("0.00"),
        nullable=False,
    )

    # ========================================================
    # DISCOUNT
    # ========================================================

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(
            12,
            2,
        ),
        default=Decimal("0.00"),
        nullable=False,
    )

    # ========================================================
    # GRAND TOTAL
    # ========================================================

    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(
            12,
            2,
        ),
        default=Decimal("0.00"),
        nullable=False,
    )

    # ========================================================
    # PAYMENT
    # ========================================================

    payment_mode: Mapped[PaymentMode] = mapped_column(
        Enum(
            PaymentMode,
            name="payment_mode",
            values_callable=lambda enum_class: [
                member.value
                for member in enum_class
            ],
        ),
        default=PaymentMode.online,
        nullable=False,
    )

    # ========================================================
    # ADDITIONAL INFORMATION
    # ========================================================

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    exhibition_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # ========================================================
    # FILES
    # ========================================================

    product_photo_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    pdf_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

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

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.id",
    )

    messages: Mapped[list["MessageLog"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )

    # ========================================================
    # CALCULATED VALUES
    # ========================================================

    @property
    def quantity(self) -> int:
        """
        Number of individually priced products.
        """

        return len(
            self.items
        )

    # ========================================================
    # GST-INCLUSIVE SUBTOTAL
    # ========================================================

    @property
    def subtotal(self) -> Decimal:
        """
        Sum of all entered customer-facing product prices.

        Product prices already include GST.
        """

        return _money(
            sum(
                (
                    _money(
                        item.unit_price
                    )
                    for item in self.items
                ),
                Decimal("0.00"),
            )
        )

    # ========================================================
    # DISCOUNTED SUBTOTAL
    # ========================================================

    @property
    def discounted_subtotal(
        self,
    ) -> Decimal:
        """
        Customer-facing amount after discount.

        GST is calculated from the amount actually charged.
        """

        discount = _money(
            self.discount_amount
        )

        value = (
            self.subtotal
            - discount
        )

        return max(
            Decimal("0.00"),
            _money(
                value
            ),
        )

    # ========================================================
    # TAXABLE VALUE
    # ========================================================

    @property
    def taxable_value(
        self,
    ) -> Decimal:
        """
        Extract taxable value from GST-inclusive amount.

        Formula:

            taxable =
                inclusive / (1 + GST / 100)

        Example:

            ₹1,180 at 18%

            ₹1,180 / 1.18 = ₹1,000
        """

        amount = (
            self.discounted_subtotal
        )

        # ----------------------------------------------------
        # GST disabled
        # ----------------------------------------------------

        if not self.gst_enabled:
            return _money(
                amount
            )

        # ----------------------------------------------------
        # GST enabled but rate is zero
        # ----------------------------------------------------

        rate = _money(
            self.tax_percent
        )

        if rate <= Decimal("0.00"):
            return _money(
                amount
            )

        divisor = (
            Decimal("1.00")
            + (
                rate
                / Decimal("100.00")
            )
        )

        return _money(
            amount / divisor
        )

    # ========================================================
    # GST AMOUNT
    # ========================================================

    @property
    def tax_amount(
        self,
    ) -> Decimal:
        """
        GST extracted from the GST-inclusive customer amount.

        GST is NOT added to the invoice total.
        """

        # ----------------------------------------------------
        # GST disabled
        # ----------------------------------------------------

        if not self.gst_enabled:
            return Decimal("0.00")

        rate = _money(
            self.tax_percent
        )

        if rate <= Decimal("0.00"):
            return Decimal("0.00")

        amount = (
            self.discounted_subtotal
            - self.taxable_value
        )

        return max(
            Decimal("0.00"),
            _money(
                amount
            ),
        )

    # ========================================================
    # CGST RATE
    # ========================================================

    @property
    def cgst_rate(
        self,
    ) -> Decimal:
        """
        Half of the total GST rate.
        """

        if not self.gst_enabled:
            return Decimal("0.00")

        return _money(
            self.tax_percent
            / Decimal("2.00")
        )

    # ========================================================
    # CGST AMOUNT
    # ========================================================

    @property
    def cgst_amount(
        self,
    ) -> Decimal:
        """
        Half of the total GST amount.
        """

        if not self.gst_enabled:
            return Decimal("0.00")

        return _money(
            self.tax_amount
            / Decimal("2.00")
        )

    # ========================================================
    # SGST RATE
    # ========================================================

    @property
    def sgst_rate(
        self,
    ) -> Decimal:
        """
        Half of the total GST rate.
        """

        if not self.gst_enabled:
            return Decimal("0.00")

        return _money(
            self.tax_percent
            / Decimal("2.00")
        )

    # ========================================================
    # SGST AMOUNT
    # ========================================================

    @property
    def sgst_amount(
        self,
    ) -> Decimal:
        """
        Remaining GST amount after CGST rounding.

        Using the remainder avoids a one-paise rounding
        mismatch.
        """

        if not self.gst_enabled:
            return Decimal("0.00")

        return _money(
            self.tax_amount
            - self.cgst_amount
        )

    # ========================================================
    # GST BREAKUP
    # ========================================================

    @property
    def gst_breakup(
        self,
    ) -> dict:
        """
        Complete GST breakup used by API and PDF generation.
        """

        return {
            "gst_enabled": (
                self.gst_enabled
            ),
            "gst_rate": _money(
                self.tax_percent
            ),
            "taxable_value": (
                self.taxable_value
            ),
            "gst_amount": (
                self.tax_amount
            ),
            "cgst_rate": (
                self.cgst_rate
            ),
            "cgst_amount": (
                self.cgst_amount
            ),
            "sgst_rate": (
                self.sgst_rate
            ),
            "sgst_amount": (
                self.sgst_amount
            ),
            "inclusive": True,
        }

    # ========================================================
    # FINAL TOTAL
    # ========================================================

    @property
    def total(
        self,
    ) -> Decimal:
        """
        Final customer payable amount.

        Product prices are already GST-inclusive.

        Therefore:

            total = subtotal - discount

        GST must NOT be added again.
        """

        return max(
            Decimal("0.00"),
            _money(
                self.subtotal
                - _money(
                    self.discount_amount
                )
            ),
        )

    # ========================================================
    # CALCULATE GRAND TOTAL
    # ========================================================

    def calculate_grand_total(
        self,
    ) -> Decimal:
        """
        Calculate the final amount that should be stored
        in the database grand_total column.
        """

        return _money(
            self.total
        )

    # ========================================================
    # UPDATE GRAND TOTAL
    # ========================================================

    def update_grand_total(
        self,
    ) -> None:
        """
        Update the persisted grand_total value.

        This must be called before saving the invoice.
        """

        self.grand_total = (
            self.calculate_grand_total()
        )


# ============================================================
# INVOICE ITEM
# ============================================================


class InvoiceItem(Base):
    """
    One individually priced item inside an invoice.

    unit_price is the final customer-facing GST-inclusive price.
    """

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey(
            "invoices.id"
        ),
        nullable=False,
        index=True,
    )

    invoice: Mapped["Invoice"] = relationship(
        back_populates="items",
    )

    product_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    item_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(
            12,
            2,
        ),
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
        ForeignKey(
            "invoices.id"
        ),
        nullable=False,
    )

    invoice: Mapped["Invoice"] = relationship(
        back_populates="messages",
    )

    channel: Mapped[MessageChannel] = mapped_column(
        Enum(
            MessageChannel,
            name="message_channel",
            values_callable=lambda enum_class: [
                member.value
                for member in enum_class
            ],
        ),
        nullable=False,
    )

    status: Mapped[MessageStatus] = mapped_column(
        Enum(
            MessageStatus,
            name="message_status",
            values_callable=lambda enum_class: [
                member.value
                for member in enum_class
            ],
        ),
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