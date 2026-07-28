"""Add P0 M3 anonymous presales conversation state and evidence.

Revision ID: 20260726_04
Revises: 20260724_03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260726_04"
down_revision = "20260724_03"
branch_labels = None
depends_on = None
OWNER = "ecomagent:created-by-20260726_04"

def _columns(inspector, table):
    return {row["name"]: row for row in inspector.get_columns(table)}

def _type_name(value):
    return str(value).lower()

def _assert_columns(inspector, table, expected):
    actual = _columns(inspector, table)
    for name, (kind, nullable) in expected.items():
        if name not in actual:
            raise RuntimeError(f"Incompatible existing schema: missing column {table}.{name}")
        found = actual[name]
        if kind not in _type_name(found["type"]) or bool(found["nullable"]) != nullable:
            raise RuntimeError(f"Incompatible existing schema: {table}.{name} expected {kind}, nullable={nullable}; found {found['type']}, nullable={found['nullable']}")

def _assert_foreign_keys(inspector, table, expected):
    actual = {(tuple(row.get("constrained_columns") or ()), row.get("referred_table"),
        tuple(row.get("referred_columns") or ())) for row in inspector.get_foreign_keys(table)}
    for item in expected:
        if item not in actual:
            raise RuntimeError(f"Incompatible existing schema: missing foreign key on {table}: {item}")

def _assert_unique(inspector, table, columns):
    actual = {tuple(row.get("column_names") or ()) for row in inspector.get_unique_constraints(table)}
    actual |= {tuple(row.get("column_names") or ()) for row in inspector.get_indexes(table) if row.get("unique")}
    if tuple(columns) not in actual:
        raise RuntimeError(f"Incompatible existing schema: missing unique constraint on {table}: {tuple(columns)}")

def _ensure_unique(inspector, table, name, columns):
    actual = {tuple(row.get("column_names") or ()) for row in inspector.get_unique_constraints(table)}
    actual |= {tuple(row.get("column_names") or ()) for row in inspector.get_indexes(table) if row.get("unique")}
    if tuple(columns) in actual:
        return
    grouped = ", ".join(f'"{column}"' for column in columns)
    duplicates = op.get_bind().execute(sa.text(
        f'SELECT count(*) FROM (SELECT 1 FROM "{table}" WHERE "{columns[0]}" IS NOT NULL GROUP BY {grouped} HAVING count(*) > 1) duplicates')).scalar_one()
    if duplicates:
        raise RuntimeError(f"Incompatible existing schema: {table}{tuple(columns)} has duplicate values")
    op.create_unique_constraint(name, table, columns)
def _mark_table(table):
    op.execute(sa.text(f"COMMENT ON TABLE {table} IS '{OWNER}'"))

def _table_owned(table):
    return op.get_bind().execute(sa.text("SELECT obj_description(to_regclass(:table), 'pg_class')"), {"table": table}).scalar() == OWNER

def _add_column(inspector, table, column):
    if column.name in _columns(inspector, table): return False
    op.add_column(table, column)
    op.execute(sa.text(f"COMMENT ON COLUMN {table}.{column.name} IS '{OWNER}'"))
    return True

def _column_owned(table, column):
    sql = "SELECT col_description(to_regclass(:table), attnum) FROM pg_attribute WHERE attrelid=to_regclass(:table) AND attname=:column"
    return op.get_bind().execute(sa.text(sql), {"table": table, "column": column}).scalar() == OWNER

def _ensure_index(inspector, table, name, columns, unique=False):
    indexes = {row["name"]: row for row in inspector.get_indexes(table)}
    if name in indexes:
        row = indexes[name]
        if tuple(row.get("column_names") or ()) != tuple(columns) or bool(row.get("unique")) != unique:
            raise RuntimeError(f"Incompatible existing schema: index {name}")
        return
    op.create_index(name, table, columns, unique=unique)

def upgrade():
    bind = op.get_bind(); inspector = sa.inspect(bind)
    if "conversations" not in inspector.get_table_names():
        raise RuntimeError("Incompatible existing schema: conversations table is required from 20260724_03")
    _add_column(inspector, "conversations", sa.Column("product_id", sa.Integer(), nullable=True))
    inspector = sa.inspect(bind)
    _add_column(inspector, "conversations", sa.Column("token_digest", sa.String(64), nullable=True))
    inspector = sa.inspect(bind)
    _add_column(inspector, "conversations", sa.Column("last_risk_level", sa.String(16), nullable=True))
    inspector = sa.inspect(bind)
    _add_column(inspector, "conversations", sa.Column("transfer_reason", sa.String(128), nullable=True))
    inspector = sa.inspect(bind)
    _assert_columns(inspector, "conversations", {"product_id": ("integer", True), "token_digest": ("varchar", True),
        "last_risk_level": ("varchar", True), "transfer_reason": ("varchar", True)})
    foreign_keys = {(tuple(row.get("constrained_columns") or ()), row.get("referred_table"))
        for row in inspector.get_foreign_keys("conversations")}
    if (("product_id",), "products") not in foreign_keys:
        orphan_count = bind.execute(sa.text("SELECT count(*) FROM conversations c LEFT JOIN products p ON c.product_id=p.id WHERE c.product_id IS NOT NULL AND p.id IS NULL")).scalar_one()
        if orphan_count: raise RuntimeError("Incompatible existing schema: orphan conversations.product_id")
        op.create_foreign_key("fk_conversations_product_id_products", "conversations", "products", ["product_id"], ["id"])
    bind.execute(sa.text("UPDATE conversations SET status='open' WHERE status='active'"))
    op.alter_column("conversations", "status", existing_type=sa.String(32), nullable=False, server_default="open")
    inspector = sa.inspect(bind)
    _ensure_index(inspector, "conversations", "ix_conversations_product_id", ["product_id"])
    inspector = sa.inspect(bind)
    _ensure_index(inspector, "conversations", "ix_conversations_status", ["status"])
    inspector = sa.inspect(bind)
    _ensure_unique(inspector, "conversations", "uq_conversations_token_digest", ["token_digest"])

    inspector = sa.inspect(bind)
    if "conversation_messages" not in inspector.get_table_names():
        op.create_table("conversation_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id"), nullable=False),
            sa.Column("sender_type", sa.String(32), nullable=False),
            sa.Column("message_type", sa.String(32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("visible_to_customer", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        _mark_table("conversation_messages")
    else:
        _assert_columns(inspector, "conversation_messages", {"id": ("integer", False), "conversation_id": ("integer", False),
            "sender_type": ("varchar", False), "message_type": ("varchar", False), "content": ("text", False),
            "visible_to_customer": ("boolean", False), "actor_id": ("integer", True), "created_at": ("timestamp", False)})
        _assert_foreign_keys(inspector, "conversation_messages", {(("conversation_id",), "conversations", ("id",)),
            (("actor_id",), "users", ("id",))})
    inspector = sa.inspect(bind)
    _ensure_index(inspector, "conversation_messages", "ix_conversation_messages_conversation_id", ["conversation_id"])
    inspector = sa.inspect(bind)
    _ensure_index(inspector, "conversation_messages", "ix_conversation_messages_actor_id", ["actor_id"])

    inspector = sa.inspect(bind)
    if "conversation_decisions" not in inspector.get_table_names():
        op.create_table("conversation_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id"), nullable=False),
            sa.Column("customer_message_id", sa.Integer(), sa.ForeignKey("conversation_messages.id"), nullable=False),
            sa.Column("risk_level", sa.String(16), nullable=False),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("reason_code", sa.String(64), nullable=False),
            sa.Column("source_summary", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("provider_status", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("customer_message_id", name="uq_conversation_decision_message"))
        _mark_table("conversation_decisions")
    else:
        _assert_columns(inspector, "conversation_decisions", {"id": ("integer", False), "conversation_id": ("integer", False),
            "customer_message_id": ("integer", False), "risk_level": ("varchar", False), "decision": ("varchar", False),
            "reason_code": ("varchar", False), "source_summary": ("text", False), "provider_status": ("varchar", True),
            "created_at": ("timestamp", False)})
        _assert_foreign_keys(inspector, "conversation_decisions", {(("conversation_id",), "conversations", ("id",)),
            (("customer_message_id",), "conversation_messages", ("id",))})
        _assert_unique(inspector, "conversation_decisions", ["customer_message_id"])
    inspector = sa.inspect(bind)
    _ensure_index(inspector, "conversation_decisions", "ix_conversation_decisions_conversation_id", ["conversation_id"])

    inspector = sa.inspect(bind)
    if "conversation_fact_sources" not in inspector.get_table_names():
        op.create_table("conversation_fact_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("decision_id", sa.Integer(), sa.ForeignKey("conversation_decisions.id"), nullable=False),
            sa.Column("source_type", sa.String(32), nullable=False),
            sa.Column("source_object_id", sa.Integer(), nullable=False),
            sa.Column("source_version", sa.String(64), nullable=False),
            sa.Column("field_summary", sa.Text(), nullable=False),
            sa.Column("data_time", sa.DateTime(), nullable=False))
        _mark_table("conversation_fact_sources")
    else:
        _assert_columns(inspector, "conversation_fact_sources", {"id": ("integer", False), "decision_id": ("integer", False),
            "source_type": ("varchar", False), "source_object_id": ("integer", False), "source_version": ("varchar", False),
            "field_summary": ("text", False), "data_time": ("timestamp", False)})
        _assert_foreign_keys(inspector, "conversation_fact_sources", {(("decision_id",), "conversation_decisions", ("id",))})
    inspector = sa.inspect(bind)
    _ensure_index(inspector, "conversation_fact_sources", "ix_conversation_fact_sources_decision_id", ["decision_id"])

def downgrade():
    bind = op.get_bind(); inspector = sa.inspect(bind)
    for column in ("transfer_reason", "last_risk_level", "token_digest", "product_id"):
        if column in _columns(inspector, "conversations") and not _column_owned("conversations", column):
            raise RuntimeError(f"Refusing downgrade: conversations.{column} was not created by {revision}")
    for table in ("conversation_fact_sources", "conversation_decisions", "conversation_messages"):
        if table in inspector.get_table_names() and not _table_owned(table):
            raise RuntimeError(f"Refusing downgrade: {table} was not created by {revision}")
    for table in ("conversation_fact_sources", "conversation_decisions", "conversation_messages"):
        inspector = sa.inspect(bind)
        if table in inspector.get_table_names(): op.drop_table(table)
    inspector = sa.inspect(bind)
    uniques = {row.get("name") for row in inspector.get_unique_constraints("conversations")}
    if "uq_conversations_token_digest" in uniques:
        op.drop_constraint("uq_conversations_token_digest", "conversations", type_="unique")
    inspector = sa.inspect(bind)
    for name in ("ix_conversations_status", "ix_conversations_product_id"):
        if name in {row["name"] for row in inspector.get_indexes("conversations")}: op.drop_index(name, table_name="conversations")
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("conversations"):
        if tuple(fk.get("constrained_columns") or ()) == ("product_id",): op.drop_constraint(fk["name"], "conversations", type_="foreignkey")
    for column in ("transfer_reason", "last_risk_level", "token_digest", "product_id"):
        if column in _columns(sa.inspect(bind), "conversations"):
            op.drop_column("conversations", column)
    op.alter_column("conversations", "status", existing_type=sa.String(32), nullable=False, server_default="active")
