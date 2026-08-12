"""Pytest configuration and fixtures for EcomAgent tests."""

import os

# This executes before app.core.config is imported below. It affects pytest
# only; normal application startup retains backend/.env loading.
os.environ["ECOMAGENT_TEST_MODE"] = "1"

import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.product import ProductCategory
from app.core.security import create_access_token, hash_password


# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
TEST_USERS = {
    "admin": ("test-admin-password", "admin"),
    "operator_content": ("test-operator-password", "operator_content"),
    "customer_service": ("test-service-password", "customer_service"),
}


def _reset_rate_limiter() -> None:
    """Keep the application's in-memory limiter from leaking across tests."""
    current = app.middleware_stack
    while current is not None:
        clients = getattr(current, "_clients", None)
        if isinstance(clients, dict):
            clients.clear()
        current = getattr(current, "app", None)


@pytest.fixture(autouse=True)
def setup_database(monkeypatch, tmp_path):
    """Create all tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    _reset_rate_limiter()
    seed_session = TestSessionLocal()
    try:
        for username, (password, role) in TEST_USERS.items():
            seed_session.add(User(username=username, password_hash=hash_password(password), role=role))
        for category in (
            "Demo",
            "服装",
            "数码",
            "食品",
            "图书",
            "美妆",
            "鞋类",
            "测试",
            "居家收纳用品/衣物收纳",
            "居家收纳用品/桌面收纳",
            "居家收纳用品/旅行收纳",
        ):
            seed_session.add(ProductCategory(name=category, is_active=True))
        seed_session.commit()
    finally:
        seed_session.close()
    # Tests never inherit keys from the machine or access a real provider.
    from app.core.config import settings
    from app.services import image_service

    isolated_upload_dir = tmp_path / "uploads"
    isolated_upload_dir.mkdir()
    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(isolated_upload_dir))
    for key in ("google_api_key", "llm_api_key", "image_gen_api_key", "llm_api_base", "image_gen_api_base", "llm_model"):
        monkeypatch.setattr(settings, key, "")
    def deny_network(*_args, **_kwargs):
        raise AssertionError("Tests must not access external model providers")
    monkeypatch.setattr(httpx, "post", deny_network)
    yield
    _reset_rate_limiter()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a test database session with automatic rollback."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with test database override."""
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        admin = db_session.query(User).filter(User.username == "admin").one()
        test_client.headers.update({"Authorization": f"Bearer {create_access_token(admin)}"})
        yield test_client

    app.dependency_overrides.clear()
