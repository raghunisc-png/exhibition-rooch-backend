"""
Move product data off invoices into invoice_items.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-14

The Invoice model dropped its single product_name/quantity/unit_price
columns in favor of a one-to-many InvoiceItem table (multiple
individually priced products per invoice), but that table was never
actually created by a migration - 0002/0003 only ever added
payment_mode/gst_enabled/grand_total. The live database was therefore
still on the old single-product schema, causing NOT NULL violations on
product_name for any insert going through the new ORM model.

This migration:

    1. Creates invoice_items.
    2. Backfills one item per existing invoice per unit of quantity,
       using its old product_name/unit_price, so historical invoices
       keep the same subtotal under the new per-item model.
    3. Recalculates grand_total for existing invoices from the
       backfilled items (mirrors Invoice.total: sum(items) - discount).
    4. Drops the now-unused product_name/quantity/unit_price columns.
    5. Also makes customer_phone nullable, matching the ORM model/API
       schema (same class of drift as above - was never migrated
       either).
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION
# ============================================================

revision = "0004"

down_revision = "0003"

branch_labels = None

depends_on = None


# ============================================================
# UPGRADE
# ============================================================


def upgrade() -> None:
    bind = op.get_bind()

    # --------------------------------------------------------
    # CREATE invoice_items
    # --------------------------------------------------------

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("item_number", sa.Integer(), nullable=False),
        sa.Column(
            "unit_price",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
    )

    # --------------------------------------------------------
    # BACKFILL existing invoices into invoice_items
    # --------------------------------------------------------

    existing_invoices = bind.execute(
        sa.text(
            """
            SELECT id, product_name, quantity, unit_price, discount_amount
            FROM invoices
            """
        )
    ).fetchall()

    for invoice in existing_invoices:
        quantity = invoice.quantity or 1

        for item_number in range(1, quantity + 1):
            bind.execute(
                sa.text(
                    """
                    INSERT INTO invoice_items
                        (invoice_id, product_name, item_number, unit_price)
                    VALUES
                        (:invoice_id, :product_name, :item_number, :unit_price)
                    """
                ),
                {
                    "invoice_id": invoice.id,
                    "product_name": invoice.product_name,
                    "item_number": item_number,
                    "unit_price": invoice.unit_price,
                },
            )

        grand_total = max(
            invoice.unit_price * quantity - invoice.discount_amount,
            0,
        )

        bind.execute(
            sa.text(
                "UPDATE invoices SET grand_total = :grand_total WHERE id = :id"
            ),
            {"grand_total": grand_total, "id": invoice.id},
        )

    # --------------------------------------------------------
    # DROP old single-product columns
    # --------------------------------------------------------

    op.drop_column("invoices", "product_name")
    op.drop_column("invoices", "quantity")
    op.drop_column("invoices", "unit_price")

    # --------------------------------------------------------
    # customer_phone is optional in the model/API - match it
    # --------------------------------------------------------

    op.alter_column(
        "invoices",
        "customer_phone",
        existing_type=sa.String(20),
        nullable=True,
    )


# ============================================================
# DOWNGRADE
# ============================================================


def downgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "invoices",
        sa.Column("product_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("quantity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "unit_price",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
    )

    first_items = bind.execute(
        sa.text(
            """
            SELECT DISTINCT ON (invoice_id)
                invoice_id, product_name, unit_price
            FROM invoice_items
            ORDER BY invoice_id, item_number
            """
        )
    ).fetchall()

    counts = bind.execute(
        sa.text(
            "SELECT invoice_id, COUNT(*) AS item_count FROM invoice_items GROUP BY invoice_id"
        )
    ).fetchall()
    counts_by_invoice = {row.invoice_id: row.item_count for row in counts}

    for item in first_items:
        bind.execute(
            sa.text(
                """
                UPDATE invoices
                SET product_name = :product_name,
                    unit_price = :unit_price,
                    quantity = :quantity
                WHERE id = :id
                """
            ),
            {
                "product_name": item.product_name,
                "unit_price": item.unit_price,
                "quantity": counts_by_invoice.get(item.invoice_id, 1),
                "id": item.invoice_id,
            },
        )

    op.alter_column(
        "invoices",
        "product_name",
        existing_type=sa.String(200),
        nullable=False,
    )
    op.alter_column(
        "invoices",
        "quantity",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "invoices",
        "unit_price",
        existing_type=sa.Numeric(precision=12, scale=2),
        nullable=False,
    )

    op.alter_column(
        "invoices",
        "customer_phone",
        existing_type=sa.String(20),
        nullable=False,
    )

    op.drop_table("invoice_items")
