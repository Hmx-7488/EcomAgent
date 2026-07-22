"""Database engine and session factory with connection pooling."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# SQLite requires check_same_thread=False; other backends use connection pooling
_is_sqlite = "sqlite" in settings.database_url

_engine_kwargs = {
    "echo": settings.debug,
    "pool_pre_ping": True,  # Verify connections before use
}

if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
    _engine_kwargs["pool_recycle"] = 3600  # Recycle connections hourly

engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session with guaranteed close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
