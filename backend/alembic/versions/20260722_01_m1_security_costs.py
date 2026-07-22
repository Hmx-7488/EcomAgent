"""M1 local account roles and SKU costs.

Revision ID: 20260722_01
Revises:
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa
revision = "20260722_01"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    # This repository pre-dates Alembic.  Existing private databases can
    # already have fact tables from SQLAlchemy; fresh deployments have none.
    # The first migration therefore creates only missing tables.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("products"):
        op.create_table("products", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("category", sa.String(128), nullable=False), sa.Column("brand", sa.String(128)), sa.Column("description", sa.Text()), sa.Column("selling_points", sa.Text()), sa.Column("parameters_json", sa.Text()), sa.Column("shipping_rule_text", sa.Text()), sa.Column("status", sa.String(32)), sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    if not inspector.has_table("skus"):
        op.create_table("skus", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("sku_name", sa.String(255), nullable=False), sa.Column("color", sa.String(64)), sa.Column("size", sa.String(64)), sa.Column("spec", sa.String(128)), sa.Column("price", sa.Float(), nullable=False), sa.Column("image_url", sa.String(512)), sa.Column("status", sa.String(32)), sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not inspector.has_table("inventory"):
        op.create_table("inventory", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("sku_id", sa.Integer(), sa.ForeignKey("skus.id"), nullable=False, unique=True), sa.Column("stock_quantity", sa.Integer()), sa.Column("locked_quantity", sa.Integer()), sa.Column("safety_stock", sa.Integer()), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    if not inspector.has_table("users"):
        op.create_table("users", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("username",sa.String(64),nullable=False,unique=True), sa.Column("password_hash",sa.String(256),nullable=False), sa.Column("role",sa.String(32),nullable=False), sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()), sa.Column("created_at",sa.DateTime(),server_default=sa.func.now()))
    if not inspector.has_table("sku_costs"):
        op.create_table("sku_costs", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("sku_id",sa.Integer(),sa.ForeignKey("skus.id"),nullable=False,unique=True), sa.Column("purchase_cost",sa.Float()), sa.Column("packaging_cost",sa.Float()), sa.Column("shipping_subsidy",sa.Float()), sa.Column("platform_fee",sa.Float()), sa.Column("marketing_allocation",sa.Float()), sa.Column("after_sales_loss",sa.Float()), sa.Column("updated_at",sa.DateTime(),server_default=sa.func.now()))
def downgrade():
    op.drop_table("sku_costs"); op.drop_table("users"); op.drop_table("inventory"); op.drop_table("skus"); op.drop_table("products")
