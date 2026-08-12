"""Add the first-level product category dictionary.

Revision ID: 20260811_05
Revises: 20260726_04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_05"
down_revision = "20260726_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_product_categories_name"),
    )
    op.create_index(
        "ix_product_categories_is_active",
        "product_categories",
        ["is_active"],
        unique=False,
    )

    bind = op.get_bind()
    existing_names = {
        str(row[0]).strip()
        for row in bind.execute(sa.text("SELECT category FROM products"))
        if row[0] is not None and str(row[0]).strip()
    }
    category_table = sa.table(
        "product_categories",
        sa.column("name", sa.String(length=128)),
        sa.column("is_active", sa.Boolean()),
    )
    if existing_names:
        op.bulk_insert(
            category_table,
            [{"name": name, "is_active": True} for name in sorted(existing_names)],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_product_categories_is_active", table_name="product_categories"
    )
    op.drop_table("product_categories")
