"""Complete the migration-owned P0 schema without runtime create_all.

Revision ID: 20260724_03
Revises: 20260722_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_03"
down_revision = "20260722_02"
branch_labels = None
depends_on = None

TABLE_OWNER_MARKER = "ecomagent:created-by-20260724_03"


def _columns(inspector, table):
    return {column["name"]: column for column in inspector.get_columns(table)}


def _type_name(type_):
    name = str(type_).lower()
    return "double precision" if name == "float" else name


def _assert_columns(inspector, table, expected):
    actual = _columns(inspector, table)
    for name, (type_name, nullable) in expected.items():
        column = actual.get(name)
        if column is None:
            raise RuntimeError(f"Incompatible existing schema: missing column {table}.{name}")
        if _type_name(column["type"]) != type_name or bool(column["nullable"]) != nullable:
            raise RuntimeError(
                f"Incompatible existing schema: {table}.{name} expected {type_name}, nullable={nullable}; "
                f"found {_type_name(column['type'])}, nullable={bool(column['nullable'])}"
            )


def _assert_foreign_keys(inspector, table, expected):
    actual = {
        (tuple(item.get("constrained_columns") or []), item.get("referred_table"), tuple(item.get("referred_columns") or []))
        for item in inspector.get_foreign_keys(table)
    }
    for item in expected:
        if item not in actual:
            raise RuntimeError(f"Incompatible existing schema: missing foreign key on {table}: {item}")


def _assert_unique(inspector, table, expected):
    actual = {tuple(item.get("column_names") or []) for item in inspector.get_unique_constraints(table)}
    actual |= {tuple(item.get("column_names") or []) for item in inspector.get_indexes(table) if item.get("unique")}
    for item in expected:
        if item not in actual:
            raise RuntimeError(f"Incompatible existing schema: missing unique constraint on {table}: {item}")


def _ensure_unique(inspector, name, table, columns):
    expected = tuple(columns)
    actual = {tuple(item.get("column_names") or []) for item in inspector.get_unique_constraints(table)}
    actual |= {tuple(item.get("column_names") or []) for item in inspector.get_indexes(table) if item.get("unique")}
    if expected in actual:
        return
    grouped = ", ".join(f'"{column}"' for column in columns)
    duplicates = op.get_bind().execute(
        sa.text(f'SELECT count(*) FROM (SELECT 1 FROM "{table}" GROUP BY {grouped} HAVING count(*) > 1) duplicates')
    ).scalar_one()
    if duplicates:
        raise RuntimeError(
            f"Incompatible existing schema: {table}{expected} has {duplicates} duplicate groups; "
            "refusing to add unique constraint"
        )
    op.create_unique_constraint(name, table, columns)


def _ensure_index(inspector, table, name, columns):
    actual = {item["name"]: tuple(item.get("column_names") or []) for item in inspector.get_indexes(table)}
    if name not in actual:
        op.create_index(name, table, columns)
    elif actual[name] != tuple(columns):
        raise RuntimeError(f"Incompatible existing schema: index {name} has columns {actual[name]}, expected {tuple(columns)}")


def _ensure_foreign_key(inspector, name, source_table, source_column, target_table, target_column):
    expected = ((source_column,), target_table, (target_column,))
    actual = {
        (tuple(item.get("constrained_columns") or []), item.get("referred_table"), tuple(item.get("referred_columns") or []))
        for item in inspector.get_foreign_keys(source_table)
    }
    if expected in actual:
        return
    bind = op.get_bind()
    orphan_count = bind.execute(
        sa.text(
            f'SELECT count(*) FROM "{source_table}" source '
            f'LEFT JOIN "{target_table}" target ON source."{source_column}" = target."{target_column}" '
            f'WHERE source."{source_column}" IS NOT NULL AND target."{target_column}" IS NULL'
        )
    ).scalar_one()
    if orphan_count:
        raise RuntimeError(
            f"Incompatible existing schema: {source_table}.{source_column} has {orphan_count} orphan references; "
            "refusing to add foreign key"
        )
    op.create_foreign_key(name, source_table, target_table, [source_column], [target_column])


def _set_not_null_if_safe(table, column, type_):
    bind = op.get_bind()
    null_count = bind.execute(sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL')).scalar_one()
    if null_count:
        raise RuntimeError(
            f"Incompatible existing schema: {table}.{column} has {null_count} NULL rows; refusing destructive NOT NULL change"
        )
    op.alter_column(table, column, existing_type=type_, nullable=False)


def _remove_empty_legacy_audit_columns(inspector):
    """Remove obsolete pre-migration columns only when no row can be lost."""
    legacy_columns = {
        "content_type",
        "platform",
        "prompt_version",
        "content_json",
        "created_by",
    }
    present = sorted(legacy_columns & set(_columns(inspector, "audit_events")))
    if not present:
        return
    row_count = op.get_bind().execute(sa.text("SELECT count(*) FROM audit_events")).scalar_one()
    if row_count:
        raise RuntimeError(
            "Incompatible existing schema: audit_events contains legacy columns and "
            f"{row_count} rows; refusing to remove columns or business data"
        )
    for column in present:
        op.drop_column("audit_events", column)


def _create_generated_contents():
    op.create_table(
        "generated_contents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(64)),
        sa.Column("prompt_version", sa.String(32)),
        sa.Column("content_json", sa.Text()),
        sa.Column("created_by", sa.String(64), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def _create_conversations():
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def _create_tool_call_logs():
    op.create_table(
        "tool_call_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id")),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("arguments_json", sa.Text()),
        sa.Column("result_summary", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="success"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def _create_assets():
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32)),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime()),
    )


def _create_image_tasks():
    op.create_table(
        "image_generation_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("source_asset_id", sa.Integer(), sa.ForeignKey("assets.id")),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("style", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(128)),
        sa.Column("prompt", sa.Text()),
        sa.Column("result_asset_ids", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("provider", sa.String(64)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approval_status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("confirmed_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def _create_orders():
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_no", sa.String(64), nullable=False),
        sa.Column("buyer_name", sa.String(128)),
        sa.Column("buyer_phone", sa.String(32)),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("payment_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("shipment_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("logistics_company", sa.String(128)),
        sa.Column("logistics_tracking_no", sa.String(128)),
        sa.Column("shipping_address", sa.Text()),
        sa.Column("signed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_no", name="uq_orders_order_no"),
    )


def _create_order_items():
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("sku_id", sa.Integer(), sa.ForeignKey("skus.id")),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
    )


def _create_after_sales_rules():
    op.create_table(
        "after_sales_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("category", sa.String(128)),
        sa.Column("support_7_days", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("after_sales_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("require_evidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_refund", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_return", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_exchange", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_resend", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rule_text", sa.Text()),
    )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    creators = {
        "generated_contents": _create_generated_contents,
        "conversations": _create_conversations,
        "tool_call_logs": _create_tool_call_logs,
        "assets": _create_assets,
        "image_generation_tasks": _create_image_tasks,
        "orders": _create_orders,
        "order_items": _create_order_items,
        "after_sales_rules": _create_after_sales_rules,
    }
    for name, creator in creators.items():
        if name not in inspector.get_table_names():
            creator()
            op.execute(f'COMMENT ON TABLE "{name}" IS \'{TABLE_OWNER_MARKER}\'')
            inspector = sa.inspect(bind)

    _remove_empty_legacy_audit_columns(inspector)
    inspector = sa.inspect(bind)

    # M1/M2 created these server-default fields as nullable.  Upgrade only
    # after proving no existing business row would be invalidated.
    for table, column, type_ in [
        ("products", "status", sa.String(32)), ("products", "created_at", sa.DateTime()), ("products", "updated_at", sa.DateTime()),
        ("users", "created_at", sa.DateTime()), ("skus", "status", sa.String(32)),
        ("inventory", "stock_quantity", sa.Integer()), ("inventory", "locked_quantity", sa.Integer()),
        ("inventory", "safety_stock", sa.Integer()), ("inventory", "updated_at", sa.DateTime()),
        ("sku_costs", "updated_at", sa.DateTime()), ("content_packages", "created_at", sa.DateTime()),
        ("content_packages", "updated_at", sa.DateTime()), ("content_versions", "created_at", sa.DateTime()),
        ("approval_records", "created_at", sa.DateTime()), ("audit_events", "created_at", sa.DateTime()),
        ("image_generation_tasks", "retry_count", sa.Integer()),
        ("image_generation_tasks", "approval_status", sa.String(16)),
    ]:
        if _columns(inspector, table)[column]["nullable"]:
            _set_not_null_if_safe(table, column, type_)
            inspector = sa.inspect(bind)

    for table, name, columns in [
        ("generated_contents", "ix_generated_contents_product_id", ["product_id"]),
        ("tool_call_logs", "ix_tool_call_logs_conversation_id", ["conversation_id"]),
        ("assets", "ix_assets_product_id", ["product_id"]),
        ("image_generation_tasks", "ix_image_generation_tasks_product_id", ["product_id"]),
        ("order_items", "ix_order_items_order_id", ["order_id"]),
        ("after_sales_rules", "ix_after_sales_rules_product_id", ["product_id"]),
    ]:
        _ensure_index(inspector, table, name, columns)
        inspector = sa.inspect(bind)

    _ensure_foreign_key(inspector, "fk_assets_confirmed_by_users", "assets", "confirmed_by_id", "users", "id")
    inspector = sa.inspect(bind)
    _ensure_foreign_key(
        inspector, "fk_image_generation_tasks_confirmed_by_users", "image_generation_tasks", "confirmed_by_id", "users", "id"
    )
    inspector = sa.inspect(bind)
    _ensure_unique(inspector, "uq_content_package_version", "content_versions", ["package_id", "version_no"])
    inspector = sa.inspect(bind)

    contracts = {
        "assets": ({"id": ("integer", False), "product_id": ("integer", False), "asset_type": ("varchar(32)", False), "url": ("varchar(1024)", False)}, (("product_id",), "products", ("id",)), (("confirmed_by_id",), "users", ("id",))),
        "image_generation_tasks": ({"id": ("integer", False), "product_id": ("integer", False), "source_asset_id": ("integer", True), "status": ("varchar(32)", False), "style": ("varchar(64)", False), "approval_status": ("varchar(16)", False)}, (("product_id",), "products", ("id",)), (("source_asset_id",), "assets", ("id",)), (("confirmed_by_id",), "users", ("id",))),
        "generated_contents": ({"id": ("integer", False), "product_id": ("integer", False), "content_type": ("varchar(64)", False), "created_by": ("varchar(64)", False)}, (("product_id",), "products", ("id",)),),
        "conversations": ({"id": ("integer", False), "status": ("varchar(32)", False)},),
        "tool_call_logs": ({"id": ("integer", False), "conversation_id": ("integer", True), "tool_name": ("varchar(128)", False)}, (("conversation_id",), "conversations", ("id",)),),
        "orders": ({"id": ("integer", False), "order_no": ("varchar(64)", False), "total_amount": ("double precision", False)},),
        "order_items": ({"id": ("integer", False), "order_id": ("integer", False), "product_id": ("integer", False), "price": ("double precision", False)}, (("order_id",), "orders", ("id",)), (("product_id",), "products", ("id",))),
        "after_sales_rules": ({"id": ("integer", False), "product_id": ("integer", False), "support_7_days": ("boolean", False)}, (("product_id",), "products", ("id",)),),
    }
    for table, contract in contracts.items():
        _assert_columns(inspector, table, contract[0])
        _assert_foreign_keys(inspector, table, contract[1:])
    _assert_unique(inspector, "content_versions", [("package_id", "version_no")])
    _assert_unique(inspector, "orders", [("order_no",)])


def downgrade():
    # A table ownership comment distinguishes fresh-DB tables created by this
    # revision from historical create_all tables.  Refuse before changing
    # anything if a historical table is present; that path requires a forward
    # corrective migration and must never risk business data.
    bind = op.get_bind()
    managed_tables = [
        "tool_call_logs",
        "image_generation_tasks",
        "assets",
        "order_items",
        "after_sales_rules",
        "generated_contents",
        "orders",
        "conversations",
    ]
    for table in managed_tables:
        marker = bind.execute(
            sa.text("SELECT obj_description(to_regclass(:table), 'pg_class')"),
            {"table": table},
        ).scalar_one_or_none()
        if marker != TABLE_OWNER_MARKER:
            raise RuntimeError(
                f"Safe downgrade refused: {table} was not created by 20260724_03; "
                "historical tables and business data will not be removed"
            )

    # Restore only M1/M2 column nullability before dropping 03-owned tables.
    for table, column, type_ in [
        ("audit_events", "created_at", sa.DateTime()), ("approval_records", "created_at", sa.DateTime()),
        ("content_versions", "created_at", sa.DateTime()), ("content_packages", "updated_at", sa.DateTime()),
        ("content_packages", "created_at", sa.DateTime()), ("sku_costs", "updated_at", sa.DateTime()),
        ("inventory", "updated_at", sa.DateTime()), ("inventory", "safety_stock", sa.Integer()),
        ("inventory", "locked_quantity", sa.Integer()), ("inventory", "stock_quantity", sa.Integer()),
        ("skus", "status", sa.String(32)), ("users", "created_at", sa.DateTime()),
        ("products", "updated_at", sa.DateTime()), ("products", "created_at", sa.DateTime()), ("products", "status", sa.String(32)),
    ]:
        op.alter_column(table, column, existing_type=type_, nullable=True)
    for table in managed_tables:
        op.drop_table(table)
