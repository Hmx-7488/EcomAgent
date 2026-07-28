"""Read-only runtime guard for migration-managed application databases."""

from __future__ import annotations

import os

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


EXPECTED_HEAD = "20260726_04"


def assert_schema_current(engine: Engine) -> None:
    """Fail startup clearly when migrations have not produced the P0 schema."""
    if os.getenv("ECOMAGENT_TEST_MODE") == "1":
        return

    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    from app.core.database import Base

    missing_tables = sorted(set(Base.metadata.tables) - actual_tables)
    missing_columns = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in actual_tables:
            continue
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns.extend(
            f"{table_name}.{column.name}" for column in table.columns if column.name not in actual_columns
        )
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception as exc:
        raise RuntimeError(
            "Database schema is not migration-managed. Run `alembic upgrade head` before starting the application."
        ) from exc
    if revision != EXPECTED_HEAD or missing_tables or missing_columns:
        details = "; ".join(
            [
                f"revision={revision!r}, expected={EXPECTED_HEAD!r}",
                f"missing tables={missing_tables}" if missing_tables else "",
                f"missing columns={missing_columns}" if missing_columns else "",
            ]
        )
        raise RuntimeError(
            "Database schema is not current. Run `alembic upgrade head` before starting the application. " + details
        )
