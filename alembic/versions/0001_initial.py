"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION
# ============================================================

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# ============================================================
# ENUMS
# ============================================================

agent_role = sa.Enum(
    "admin",
    "agent",
    name="agentrole",
)

message_channel = sa.Enum(
    "whatsapp",
    "sms",
    name="messagechannel",
)

message_status = sa.Enum(
    "pending",
    "sent",
    "failed",
    "skipped",
    name="messagestatus",
)


# ============================================================
# UPGRADE
# ============================================================

def upgrade() -> None:

    # ========================================================
    # AGENTS
    # ========================================================

    op.create_table(
        "agents",

        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
        ),

        sa.Column(
            "full_name",
            sa.String(120),
            nullable=False,
        ),

        sa.Column(
            "email",
            sa.String(255),
            nullable=False,
            unique=True,
        ),

        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=False,
        ),

        sa.Column(
            "role",
            agent_role,
            nullable=False,
            server_default="agent",
        ),

        sa.Column(
            "booth_name",
            sa.String(120),
            nullable=True,
        ),

        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.utcnow(),
        ),
    )

    op.create_index(
        "ix_agents_email",
        "agents",
        ["email"],
    )

    # ========================================================
    # INVOICES
    # ========================================================

    op.create_table(
        "invoices",

        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
        ),

        # ----------------------------------------------------
        # Offline idempotency
        # ----------------------------------------------------

        sa.Column(
            "client_uuid",
            sa.String(36),
            nullable=False,
        ),

        sa.Column(
            "invoice_number",
            sa.String(40),
            nullable=False,
            unique=True,
        ),

        # ----------------------------------------------------
        # Agent
        # ----------------------------------------------------

        sa.Column(
            "agent_id",
            sa.Integer,
            sa.ForeignKey("agents.id"),
            nullable=False,
        ),

        # ----------------------------------------------------
        # Customer
        # ----------------------------------------------------

        sa.Column(
            "customer_name",
            sa.String(150),
            nullable=False,
        ),

        # Phone is OPTIONAL.
        sa.Column(
            "customer_phone",
            sa.String(20),
            nullable=True,
        ),

        # Email is OPTIONAL.
        sa.Column(
            "customer_email",
            sa.String(255),
            nullable=True,
        ),

        # ----------------------------------------------------
        # Invoice information
        # ----------------------------------------------------

        sa.Column(
            "product_description",
            sa.Text,
            nullable=True,
        ),

        sa.Column(
            "tax_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="0.00",
        ),

        sa.Column(
            "discount_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),

        sa.Column(
            "notes",
            sa.Text,
            nullable=True,
        ),

        sa.Column(
            "exhibition_name",
            sa.String(200),
            nullable=True,
        ),

        # ----------------------------------------------------
        # Files
        # ----------------------------------------------------

        sa.Column(
            "product_photo_path",
            sa.String(500),
            nullable=True,
        ),

        sa.Column(
            "pdf_path",
            sa.String(500),
            nullable=True,
        ),

        # ----------------------------------------------------
        # Dates
        # ----------------------------------------------------

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.utcnow(),
        ),

        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.utcnow(),
        ),

        # ----------------------------------------------------
        # Idempotency constraint
        # ----------------------------------------------------

        sa.UniqueConstraint(
            "client_uuid",
            name="uq_invoice_client_uuid",
        ),
    )

    # ========================================================
    # INVOICE INDEXES
    # ========================================================

    op.create_index(
        "ix_invoices_client_uuid",
        "invoices",
        ["client_uuid"],
    )

    op.create_index(
        "ix_invoices_invoice_number",
        "invoices",
        ["invoice_number"],
    )

    op.create_index(
        "ix_invoices_customer_phone",
        "invoices",
        ["customer_phone"],
    )

    # ========================================================
    # INVOICE ITEMS
    # ========================================================

    op.create_table(
        "invoice_items",

        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
        ),

        sa.Column(
            "invoice_id",
            sa.Integer,
            sa.ForeignKey("invoices.id"),
            nullable=False,
        ),

        # Product name is stored on the item,
        # not on the invoice.
        sa.Column(
            "product_name",
            sa.String(200),
            nullable=False,
        ),

        # UI position:
        #
        # 1
        # 2
        # 3
        # 4
        # 5
        #
        # The backend does not assign a fixed price.
        sa.Column(
            "item_number",
            sa.Integer,
            nullable=False,
        ),

        # Price manually entered by the booth agent.
        sa.Column(
            "unit_price",
            sa.Numeric(12, 2),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_invoice_items_invoice_id",
        "invoice_items",
        ["invoice_id"],
    )

    # ========================================================
    # MESSAGE LOGS
    # ========================================================

    op.create_table(
        "message_logs",

        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
        ),

        sa.Column(
            "invoice_id",
            sa.Integer,
            sa.ForeignKey("invoices.id"),
            nullable=False,
        ),

        sa.Column(
            "channel",
            message_channel,
            nullable=False,
        ),

        sa.Column(
            "status",
            message_status,
            nullable=False,
            server_default="pending",
        ),

        sa.Column(
            "provider_sid",
            sa.String(100),
            nullable=True,
        ),

        sa.Column(
            "error_message",
            sa.Text,
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.utcnow(),
        ),
    )

    op.create_index(
        "ix_message_logs_invoice_id",
        "message_logs",
        ["invoice_id"],
    )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade() -> None:

    # Drop child table first.
    op.drop_index(
        "ix_message_logs_invoice_id",
        table_name="message_logs",
    )

    op.drop_table(
        "message_logs",
    )

    # Invoice items depend on invoices.
    op.drop_index(
        "ix_invoice_items_invoice_id",
        table_name="invoice_items",
    )

    op.drop_table(
        "invoice_items",
    )

    # Invoice indexes.
    op.drop_index(
        "ix_invoices_customer_phone",
        table_name="invoices",
    )

    op.drop_index(
        "ix_invoices_invoice_number",
        table_name="invoices",
    )

    op.drop_index(
        "ix_invoices_client_uuid",
        table_name="invoices",
    )

    op.drop_table(
        "invoices",
    )

    # Agent.
    op.drop_index(
        "ix_agents_email",
        table_name="agents",
    )

    op.drop_table(
        "agents",
    )

    # PostgreSQL enums.
    message_status.drop(
        op.get_bind(),
        checkfirst=True,
    )

    message_channel.drop(
        op.get_bind(),
        checkfirst=True,
    )

    agent_role.drop(
        op.get_bind(),
        checkfirst=True,
    )