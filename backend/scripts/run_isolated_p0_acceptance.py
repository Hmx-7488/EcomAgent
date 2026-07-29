"""Run the Docker P0 verifier in a disposable PostgreSQL database.

The wrapper migrates a new database, invokes the existing workflow with local
Provider stubs, and always drops the database plus files created during the
run. It never imports application settings before test isolation is installed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIN_PASSWORD_LENGTH = 12


def _required_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise argparse.ArgumentTypeError(
            f"acceptance passwords must contain at least {MIN_PASSWORD_LENGTH} characters"
        )
    return value


def _files_under(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {path.resolve() for path in directory.rglob("*") if path.is_file()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--admin-password", required=True, type=_required_password)
    parser.add_argument("--operator-password", required=True, type=_required_password)
    parser.add_argument("--service-password", required=True, type=_required_password)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    root_url = make_url(args.database_url)
    database_name = f"ecomagent_acceptance_{uuid.uuid4().hex[:12]}"
    isolated_url = root_url.set(database=database_name)
    upload_dir = Path(os.getenv("UPLOAD_DIR", str(BACKEND_ROOT / "uploads"))).resolve()
    files_before = _files_under(upload_dir)
    engine = create_engine(root_url, isolation_level="AUTOCOMMIT")
    created = False
    workflow_passed = False
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        created = True

        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": isolated_url.render_as_string(
                    hide_password=False
                ),
                "ECOMAGENT_TEST_MODE": "1",
                "GOOGLE_API_KEY": "",
                "LLM_API_KEY": "",
                "LLM_API_BASE": "",
                "LLM_MODEL": "",
                "IMAGE_GEN_API_KEY": "",
                "IMAGE_GEN_API_BASE": "",
            }
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT,
            env=environment,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(BACKEND_ROOT / "scripts" / "verify_p0_docker_workflow.py"),
                "--database-url",
                isolated_url.render_as_string(hide_password=False),
                "--admin-password",
                args.admin_password,
                "--operator-password",
                args.operator_password,
                "--service-password",
                args.service_password,
            ],
            cwd=BACKEND_ROOT,
            env=environment,
            check=True,
        )
        workflow_passed = True
    finally:
        for path in _files_under(upload_dir) - files_before:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if created:
            with engine.connect() as connection:
                connection.exec_driver_sql(
                    f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'
                )
        engine.dispose()

    print(f"isolated_database={database_name}")
    print(f"workflow_passed={str(workflow_passed).lower()}")
    print("isolated_database_dropped=true")
    print("acceptance_uploads_cleaned=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
