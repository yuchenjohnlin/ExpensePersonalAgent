"""ledger: categories, expenses and their lines

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(10, 2)
MEASURE = sa.Numeric(16, 6)
STAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ledger_category",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("system_key", sa.Text(), nullable=True),
        sa.Column("created_at", STAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_category")),
        sa.UniqueConstraint("owner_id", "name", name="uq_ledger_category_owner_name"),
    )
    op.create_index("uq_ledger_category_owner_system_key", "ledger_category", ["owner_id", "system_key"],
                    unique=True, postgresql_where=sa.text("system_key IS NOT NULL"))
    op.create_table(
        "ledger_expense",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("merchant", sa.String(120), nullable=False),
        sa.Column("notes", sa.String(500), nullable=False),
        sa.Column("tax", MONEY, nullable=True),
        sa.Column("tip", MONEY, nullable=False),
        sa.Column("receipt_discount", MONEY, nullable=False),
        sa.Column("total_only", sa.Boolean(), nullable=False),
        sa.Column("reviewed_at", STAMP, nullable=True),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("updated_at", STAMP, nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_ledger_expense_amount_positive")),
        sa.CheckConstraint("(tax IS NULL OR tax >= 0) AND tip >= 0 AND receipt_discount >= 0",
                           name=op.f("ck_ledger_expense_adjustments_nonnegative")),
        sa.CheckConstraint("COALESCE(tax, 0) + tip < amount", name=op.f("ck_ledger_expense_tax_and_tip_below_amount")),
        sa.ForeignKeyConstraint(["category_id"], ["ledger_category.id"],
                                name=op.f("fk_ledger_expense_category_id_ledger_category"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_expense")),
    )
    op.create_index("ix_ledger_expense_owner_date", "ledger_expense", ["owner_id", "date"])
    op.create_index("ix_ledger_expense_unreviewed", "ledger_expense", ["owner_id", "id"],
                    postgresql_where=sa.text("reviewed_at IS NULL"))
    op.create_table(
        "ledger_line",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("expense_id", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", MEASURE, nullable=True),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("amount", MONEY, nullable=True),
        sa.Column("discount", MONEY, nullable=False),
        sa.Column("quoted_unit_price", MEASURE, nullable=True),
        sa.Column("price_unit", sa.String(8), nullable=False),
        sa.Column("net_weight", MEASURE, nullable=True),
        sa.Column("weight_unit", sa.String(4), nullable=False),
        sa.Column("notes", sa.String(500), nullable=False),
        sa.Column("derived_field", sa.String(20), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("updated_at", STAMP, nullable=False),
        sa.CheckConstraint("amount IS NULL OR amount >= 0", name=op.f("ck_ledger_line_amount_nonnegative")),
        sa.CheckConstraint("discount = 0 OR (amount IS NOT NULL AND discount > 0 AND discount <= amount)",
                           name=op.f("ck_ledger_line_discount_within_amount")),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name=op.f("ck_ledger_line_quantity_nonnegative")),
        sa.CheckConstraint("quoted_unit_price IS NULL OR quoted_unit_price >= 0",
                           name=op.f("ck_ledger_line_price_nonnegative")),
        sa.CheckConstraint("net_weight IS NULL OR net_weight > 0", name=op.f("ck_ledger_line_weight_positive")),
        sa.CheckConstraint("derived_field = '' OR (derived_field = 'quantity' AND quantity IS NOT NULL) "
                           "OR (derived_field = 'quoted_unit_price' AND quoted_unit_price IS NOT NULL) "
                           "OR (derived_field = 'net_weight' AND net_weight IS NOT NULL)",
                           name=op.f("ck_ledger_line_derived_value_present")),
        sa.ForeignKeyConstraint(["expense_id"], ["ledger_expense.id"],
                                name=op.f("fk_ledger_line_expense_id_ledger_expense"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_line")),
    )
    op.create_index("ix_ledger_line_expense_id", "ledger_line", ["expense_id"])


def downgrade() -> None:
    op.drop_table("ledger_line")
    op.drop_table("ledger_expense")
    op.drop_table("ledger_category")
