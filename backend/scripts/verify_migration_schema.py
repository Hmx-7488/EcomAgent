"""Verify that Alembic alone produces the complete P0 SQLAlchemy schema.

This command deliberately creates a new PostgreSQL database, runs only the
migration chain, and compares its catalog with the imported model metadata.
It then imports ``app.main`` and proves that the import does not change the
schema.  It is a Gate command, not part of the normal SQLite unit-test suite.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.schema import ForeignKeyConstraint, UniqueConstraint


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_metadata():
    """Load every mapped P0 model without importing the FastAPI application."""
    from app.core.database import Base
    import app.models.asset  # noqa: F401
    import app.models.content  # noqa: F401
    import app.models.cost  # noqa: F401
    import app.models.order  # noqa: F401
    import app.models.product  # noqa: F401
    import app.models.user  # noqa: F401

    return Base.metadata


def _type_name(type_: Any, dialect: Any) -> str:
    name = type_.compile(dialect=dialect).lower()
    # PostgreSQL reflects SQLAlchemy ``Float`` as ``double precision``.
    return "double precision" if name == "float" else name


def _schema_snapshot(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        tables: dict[str, Any] = {}
        for name in sorted(inspector.get_table_names()):
            columns = inspector.get_columns(name)
            primary_key = inspector.get_pk_constraint(name).get("constrained_columns") or []
            foreign_keys = []
            for foreign_key in inspector.get_foreign_keys(name):
                foreign_keys.append(
                    {
                        "columns": tuple(foreign_key.get("constrained_columns") or []),
                        "referred_table": foreign_key.get("referred_table"),
                        "referred_columns": tuple(foreign_key.get("referred_columns") or []),
                    }
                )
            unique_constraints = []
            for constraint in inspector.get_unique_constraints(name):
                columns_ = constraint.get("column_names") or []
                if columns_:
                    unique_constraints.append(tuple(columns_))
            unique_indexes = []
            indexes = []
            for index in inspector.get_indexes(name):
                columns_ = tuple(index.get("column_names") or [])
                if not columns_:
                    continue
                if index.get("unique"):
                    unique_indexes.append(columns_)
                else:
                    indexes.append(columns_)
            tables[name] = {
                "columns": {
                    column["name"]: {
                        "type": _type_name(column["type"], engine.dialect),
                        "nullable": bool(column["nullable"]),
                        "primary_key": column["name"] in primary_key,
                    }
                    for column in columns
                },
                "foreign_keys": sorted(foreign_keys, key=lambda item: (item["columns"], item["referred_table"] or "")),
                "unique": sorted(set(unique_constraints + unique_indexes)),
                "indexes": sorted(indexes),
            }
        return tables
    finally:
        engine.dispose()


def _metadata_snapshot(database_url: str) -> dict[str, Any]:
    metadata = _load_metadata()
    engine = create_engine(database_url)
    try:
        tables: dict[str, Any] = {}
        for table in metadata.sorted_tables:
            foreign_keys = []
            for constraint in table.constraints:
                if isinstance(constraint, ForeignKeyConstraint):
                    elements = list(constraint.elements)
                    foreign_keys.append(
                        {
                            "columns": tuple(element.parent.name for element in elements),
                            "referred_table": elements[0].column.table.name,
                            "referred_columns": tuple(element.column.name for element in elements),
                        }
                    )
            unique = [
                tuple(column.name for column in constraint.columns)
                for constraint in table.constraints
                if isinstance(constraint, UniqueConstraint)
            ]
            unique.extend((column.name,) for column in table.columns if column.unique)
            indexes = [tuple(column.name for column in index.columns) for index in table.indexes if not index.unique]
            tables[table.name] = {
                "columns": {
                    column.name: {
                        "type": _type_name(column.type, engine.dialect),
                        "nullable": bool(column.nullable),
                        "primary_key": bool(column.primary_key),
                    }
                    for column in table.columns
                },
                "foreign_keys": sorted(foreign_keys, key=lambda item: (item["columns"], item["referred_table"])),
                "unique": sorted(set(unique)),
                "indexes": sorted(indexes),
            }
        return tables
    finally:
        engine.dispose()


def _compare(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for table in sorted(set(actual) - set(expected) - {"alembic_version"}):
        issues.append(f"unexpected table: {table}")
    for table, expected_table in expected.items():
        actual_table = actual.get(table)
        if actual_table is None:
            issues.append(f"missing table: {table}")
            continue
        for column, expected_column in expected_table["columns"].items():
            actual_column = actual_table["columns"].get(column)
            if actual_column is None:
                issues.append(f"missing column: {table}.{column}")
            elif actual_column != expected_column:
                issues.append(
                    f"column mismatch: {table}.{column}; expected={expected_column}; actual={actual_column}"
                )
        for column in sorted(set(actual_table["columns"]) - set(expected_table["columns"])):
            issues.append(f"unexpected column: {table}.{column}")
        for label in ("foreign_keys", "unique", "indexes"):
            missing = [item for item in expected_table[label] if item not in actual_table[label]]
            for item in missing:
                issues.append(f"missing {label}: {table}.{item}")
            unexpected = [item for item in actual_table[label] if item not in expected_table[label]]
            for item in unexpected:
                issues.append(f"unexpected {label}: {table}.{item}")
    return issues


def _create_empty_database(root_url: str, database_name: str) -> str:
    if not database_name.startswith(("ecomagent_m21_", "ecomagent_m3_")):
        raise ValueError("verification database name must start with ecomagent_m21_ or ecomagent_m3_")
    root = make_url(root_url)
    admin_url: URL = root.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name}
            ).scalar()
            if exists:
                raise RuntimeError(f"verification database already exists: {database_name}")
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        engine.dispose()
    # ``str(URL)`` deliberately masks passwords.  Alembic needs the real URL
    # in its private subprocess environment, while this script never prints it.
    return root.set(database=database_name).render_as_string(hide_password=False)


def _run_upgrade(database_url: str) -> None:
    env = os.environ.copy()
    env.update({"DATABASE_URL": database_url, "ECOMAGENT_TEST_MODE": "1"})
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"alembic upgrade failed:\n{completed.stdout}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-url", help="PostgreSQL URL; password is never printed")
    parser.add_argument("--database-name")
    parser.add_argument("--database-url", help="Read-only check for an already-migrated PostgreSQL database")
    args = parser.parse_args()
    if args.database_url:
        if args.root_url or args.database_name:
            parser.error("--database-url cannot be combined with --root-url or --database-name")
        database_url = args.database_url
        database_name = make_url(database_url).database or "existing"
    elif args.root_url and args.database_name:
        database_url = _create_empty_database(args.root_url, args.database_name)
        database_name = args.database_name
    else:
        parser.error("provide --database-url, or both --root-url and --database-name")
    # Importing models and app.main must target the same fresh database that
    # Alembic upgraded.  This stays process-local and is never printed.
    os.environ["DATABASE_URL"] = database_url
    os.environ["ECOMAGENT_TEST_MODE"] = "1"
    expected = _metadata_snapshot(database_url)
    if not args.database_url:
        _run_upgrade(database_url)
    before_import = _schema_snapshot(database_url)
    migration_issues = _compare(expected, before_import)

    import app.main  # noqa: F401  # The Gate must prove import has no schema side effect.

    after_import = _schema_snapshot(database_url)
    import_changed_schema = before_import != after_import
    result = {
        "database": database_name,
        "expected_tables": sorted(expected),
        "migration_issues": migration_issues,
        "app_import_changed_schema": import_changed_schema,
        "import_added_tables": sorted(set(after_import) - set(before_import)),
        "import_removed_tables": sorted(set(before_import) - set(after_import)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if migration_issues or import_changed_schema else 0


if __name__ == "__main__":
    raise SystemExit(main())
