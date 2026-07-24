"""P0 M2 content, image approval and audit trail.

Revision ID: 20260722_02
Revises: 20260722_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260722_02"
down_revision = "20260722_01"
branch_labels = None
depends_on = None

def _has_column(inspector, table, column):
    return table in inspector.get_table_names() and column in {item["name"] for item in inspector.get_columns(table)}

def upgrade():
    bind = op.get_bind(); inspector = sa.inspect(bind); tables = inspector.get_table_names()
    if "content_packages" not in tables:
        op.create_table("content_packages", sa.Column("id",sa.Integer(),primary_key=True),sa.Column("product_id",sa.Integer(),sa.ForeignKey("products.id"),nullable=False),sa.Column("source_fact_version",sa.String(64),nullable=False),sa.Column("source_summary",sa.Text(),nullable=False),sa.Column("status",sa.String(16),nullable=False,server_default="draft"),sa.Column("current_version_no",sa.Integer(),nullable=False,server_default="1"),sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(),server_default=sa.func.now()))
    if "content_versions" not in tables:
        op.create_table("content_versions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("package_id",sa.Integer(),sa.ForeignKey("content_packages.id"),nullable=False),sa.Column("version_no",sa.Integer(),nullable=False),sa.Column("payload_json",sa.Text(),nullable=False),sa.Column("provider",sa.String(64),nullable=False),sa.Column("model_name",sa.String(128)),sa.Column("task_status",sa.String(32),nullable=False),sa.Column("error_summary",sa.Text()),sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(),server_default=sa.func.now()),sa.UniqueConstraint("package_id","version_no",name="uq_content_package_version"))
    if "approval_records" not in tables:
        op.create_table("approval_records",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("target_type",sa.String(32),nullable=False),sa.Column("target_id",sa.Integer(),nullable=False),sa.Column("status",sa.String(16),nullable=False),sa.Column("reason",sa.Text()),sa.Column("actor_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(),server_default=sa.func.now()))
    if "audit_events" not in tables:
        op.create_table("audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("action",sa.String(64),nullable=False),sa.Column("target_type",sa.String(32),nullable=False),sa.Column("target_id",sa.Integer(),nullable=False),sa.Column("actor_id",sa.Integer(),sa.ForeignKey("users.id")),sa.Column("before_json",sa.Text()),sa.Column("after_json",sa.Text()),sa.Column("summary",sa.Text()),sa.Column("created_at",sa.DateTime(),server_default=sa.func.now()))
    inspector = sa.inspect(bind)
    for table, column, typ in [("assets","confirmed_by_id",sa.Integer()),("assets","confirmed_at",sa.DateTime()),("image_generation_tasks","provider",sa.String(64)),("image_generation_tasks","retry_count",sa.Integer()),("image_generation_tasks","approval_status",sa.String(16)),("image_generation_tasks","rejection_reason",sa.Text()),("image_generation_tasks","confirmed_by_id",sa.Integer()),("image_generation_tasks","confirmed_at",sa.DateTime())]:
        if table in inspector.get_table_names() and not _has_column(inspector, table, column):
            op.add_column(table, sa.Column(column, typ, nullable=True))

def downgrade():
    # Historical M1 asset/task rows must remain recoverable; downgrade removes M2-only tables only.
    op.drop_table("audit_events"); op.drop_table("approval_records"); op.drop_table("content_versions"); op.drop_table("content_packages")
