"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

agent_role = sa.Enum("admin", "agent", name="agentrole")
message_channel = sa.Enum("whatsapp", "sms", name="messagechannel")
message_status = sa.Enum("pending", "sent", "failed", "skipped", name="messagestatus")


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", agent_role, nullable=False, server_default="agent"),
        sa.Column("booth_name", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agents_email", "agents", ["email"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_uuid", sa.String(36), nullable=False),
        sa.Column("invoice_number", sa.String(40), nullable=False, unique=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("customer_name", sa.String(150), nullable=False),
        sa.Column("customer_phone", sa.String(20), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("product_description", sa.Text, nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("product_photo_path", sa.String(500), nullable=True),
        sa.Column("pdf_path", sa.String(500), nullable=True),
        sa.Column("exhibition_name", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_uuid", name="uq_invoice_client_uuid"),
    )
    op.create_index("ix_invoices_client_uuid", "invoices", ["client_uuid"])
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_index("ix_invoices_customer_phone", "invoices", ["customer_phone"])

    op.create_table(
        "message_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("invoice_id", sa.Integer, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("channel", message_channel, nullable=False),
        sa.Column("status", message_status, nullable=False, server_default="pending"),
        sa.Column("provider_sid", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("message_logs")
    op.drop_table("invoices")
    op.drop_table("agents")
    message_status.drop(op.get_bind(), checkfirst=True)
    message_channel.drop(op.get_bind(), checkfirst=True)
    agent_role.drop(op.get_bind(), checkfirst=True)
