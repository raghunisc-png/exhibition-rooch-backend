"""
Make invoice_items.product_name optional.

Revision ID: 0005
Revises: 0003
Create Date: 2026-08-14

0004_invoice_items_table.py has been removed. It assumed invoice_items
didn't exist yet (true against an older local copy of 0001), but the
actual 0001_initial.py already creates invoice_items with the full
current schema - so 0004 was a redundant, conflicting CREATE TABLE that
broke every fresh deploy.
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION
# ============================================================

revision = "0005"

down_revision = "0003"

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
