"""Alembic environment configuration."""

# `alembic.exe` is installed under the virtualenv's Scripts directory, so its
# import path does not reliably include this repository's backend directory.
# Add the directory that owns the `app` package before importing application
# metadata; this also makes the documented standalone migration command work.
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

# Import all models so Alembic can detect them
import app.models.product  # noqa: F401
import app.models.content  # noqa: F401
import app.models.order    # noqa: F401
import app.models.asset    # noqa: F401
import app.models.user     # noqa: F401
import app.models.cost     # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    try:
        with context.begin_transaction():
            context.run_migrations()
    except Exception:
        # Ensure transaction is rolled back on any migration error
        raise


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        try:
            with context.begin_transaction():
                context.run_migrations()
        except Exception:
            # Transaction is automatically rolled back via context manager exit
            raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
