"""
Make invoice_items.product_name optional.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION
# ============================================================

revision = "0005"

down_revision = "0004"

branch_labels = None

depends_on = None


# ============================================================
# UPGRADE
# ============================================================


def upgrade() -> None:
    op.alter_column(
        "invoice_items",
        "product_name",
        existing_type=sa.String(200),
        nullable=True,
    )


# ============================================================
# DOWNGRADE
# ============================================================


def downgrade() -> None:
    op.execute(
        "UPDATE invoice_items SET product_name = 'Item' WHERE product_name IS NULL"
    )

    op.alter_column(
        "invoice_items",
        "product_name",
        existing_type=sa.String(200),
        nullable=False,
    )
