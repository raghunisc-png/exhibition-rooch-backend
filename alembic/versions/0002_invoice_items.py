"""
Fix invoice schema.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION
# ============================================================

revision = "0002"

down_revision = "0001"

branch_labels = None

depends_on = None


# ============================================================
# ENUMS
# ============================================================

payment_mode = sa.Enum(
    "online",
    "cash",
    name="payment_mode",
)


# ============================================================
# UPGRADE
# ============================================================


def upgrade() -> None:
    """
    Upgrade invoice schema.

    Adds:

        1. payment_mode
        2. gst_enabled
        3. grand_total

    Existing invoices are preserved.

    Existing invoices receive:

        payment_mode = online
        gst_enabled = false
        grand_total = 0.00

    The actual grand_total for old invoices can later be
    recalculated from their invoice items.
    """

    bind = op.get_bind()

    # ========================================================
    # PAYMENT MODE ENUM
    # ========================================================

    # PostgreSQL enum does not exist yet.
    payment_mode.create(
        bind,
        checkfirst=True,
    )

    # ========================================================
    # PAYMENT MODE
    # ========================================================

    op.add_column(
        "invoices",
        sa.Column(
            "payment_mode",
            payment_mode,
            nullable=False,
            server_default="online",
        ),
    )

    # Remove server default after existing rows have
    # received the value.
    op.alter_column(
        "invoices",
        "payment_mode",
        server_default=None,
    )

    # ========================================================
    # GST ENABLED
    # ========================================================

    """
    Store whether GST was enabled for this invoice.

    Existing invoices are assumed to have GST disabled.
    """

    op.add_column(
        "invoices",
        sa.Column(
            "gst_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Remove server default after existing rows have
    # received the value.
    op.alter_column(
        "invoices",
        "gst_enabled",
        server_default=None,
    )

    # ========================================================
    # GRAND TOTAL
    # ========================================================

    """
    Persist the final customer payable amount.

    Existing invoices are initialized to 0.00.

    New invoice creation will calculate and store the actual
    grand total.
    """

    op.add_column(
        "invoices",
        sa.Column(
            "grand_total",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
            server_default="0.00",
        ),
    )

    # Remove server default after existing rows have
    # received the value.
    op.alter_column(
        "invoices",
        "grand_total",
        server_default=None,
    )


# ============================================================
# DOWNGRADE
# ============================================================


def downgrade() -> None:
    """
    Reverse migration 0002.

    Removes:

        grand_total
        gst_enabled
        payment_mode
    """

    # ========================================================
    # GRAND TOTAL
    # ========================================================

    op.drop_column(
        "invoices",
        "grand_total",
    )

    # ========================================================
    # GST ENABLED
    # ========================================================

    op.drop_column(
        "invoices",
        "gst_enabled",
    )

    # ========================================================
    # PAYMENT MODE
    # ========================================================

    op.drop_column(
        "invoices",
        "payment_mode",
    )

    # ========================================================
    # PAYMENT MODE ENUM
    # ========================================================

    payment_mode.drop(
        op.get_bind(),
        checkfirst=True,
    )