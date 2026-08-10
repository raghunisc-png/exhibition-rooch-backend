"""add invoice items and update invoice structure

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10
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
# UPGRADE
# ============================================================


def upgrade() -> None:
    # --------------------------------------------------------
    # 1. Make customer phone optional
    # --------------------------------------------------------

    op.alter_column(
        "invoices",
        "customer_phone",
        existing_type=sa.String(length=20),
        nullable=True,
    )

    # --------------------------------------------------------
    # 2. Remove old single-product fields
    #
    # The old database stored:
    #
    # product_name
    # quantity
    # unit_price
    #
    # These are no longer used because every invoice can now
    # contain multiple individually priced items.
    # --------------------------------------------------------

    op.drop_column(
        "invoices",
        "product_name",
    )

    op.drop_column(
        "invoices",
        "quantity",
    )

    op.drop_column(
        "invoices",
        "unit_price",
    )

    # --------------------------------------------------------
    # 3. Create invoice_items table
    # --------------------------------------------------------

    op.create_table(
        "invoice_items",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey(
                "invoices.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        sa.Column(
            "product_name",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "item_number",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "unit_price",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
        ),
    )

    # --------------------------------------------------------
    # 4. Index invoice_id for faster invoice item lookup
    # --------------------------------------------------------

    op.create_index(
        "ix_invoice_items_invoice_id",
        "invoice_items",
        ["invoice_id"],
    )


# ============================================================
# DOWNGRADE
# ============================================================


def downgrade() -> None:
    # --------------------------------------------------------
    # 1. Remove invoice_items
    # --------------------------------------------------------

    op.drop_index(
        "ix_invoice_items_invoice_id",
        table_name="invoice_items",
    )

    op.drop_table(
        "invoice_items",
    )

    # --------------------------------------------------------
    # 2. Restore old invoice columns
    #
    # WARNING:
    # These are restored empty/default values because the
    # individual invoice item data cannot automatically be
    # reconstructed after the migration has been downgraded.
    # --------------------------------------------------------

    op.add_column(
        "invoices",
        sa.Column(
            "product_name",
            sa.String(length=200),
            nullable=True,
        ),
    )

    op.add_column(
        "invoices",
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    op.add_column(
        "invoices",
        sa.Column(
            "unit_price",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
            server_default="0",
        ),
    )

    # --------------------------------------------------------
    # 3. Restore customer phone as required
    # --------------------------------------------------------

    op.alter_column(
        "invoices",
        "customer_phone",
        existing_type=sa.String(length=20),
        nullable=False,
    )