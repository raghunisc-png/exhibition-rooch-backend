"""
Add GST enabled and grand total to invoices.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION
# ============================================================

revision = "0003"

down_revision = "0002"

branch_labels = None

depends_on = None


# ============================================================
# UPGRADE
# ============================================================


def upgrade() -> None:
    """
    Add missing GST / grand total fields to invoices.

    grand_total may already exist in the database because it
    was added by an earlier database/model change.

    Therefore this migration checks the existing database
    columns before adding anything.
    """

    bind = op.get_bind()

    inspector = sa.inspect(bind)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(
            "invoices"
        )
    }

    # --------------------------------------------------------
    # GST ENABLED
    # --------------------------------------------------------

    if "gst_enabled" not in existing_columns:

        op.add_column(
            "invoices",
            sa.Column(
                "gst_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

        # Existing rows have now received false.
        # Remove the database-level default so the application
        # remains responsible for future values.

        op.alter_column(
            "invoices",
            "gst_enabled",
            server_default=None,
        )

    # --------------------------------------------------------
    # GRAND TOTAL
    # --------------------------------------------------------

    if "grand_total" not in existing_columns:

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

        # Existing rows have now received 0.00.
        # Remove the database-level default.

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
    Remove GST enabled and grand total columns.

    Only remove columns if they exist.
    """

    bind = op.get_bind()

    inspector = sa.inspect(bind)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(
            "invoices"
        )
    }

    # --------------------------------------------------------
    # GRAND TOTAL
    # --------------------------------------------------------

    if "grand_total" in existing_columns:

        op.drop_column(
            "invoices",
            "grand_total",
        )

    # --------------------------------------------------------
    # GST ENABLED
    # --------------------------------------------------------

    if "gst_enabled" in existing_columns:

        op.drop_column(
            "invoices",
            "gst_enabled",
        )