"""Provider failure states are deterministic and never require a real call."""

import httpx
import pytest

from app.models.product import Product
from app.services.image_service import create_generation_task, process_generation_task


def _task(db_session):
    product = Product(name="provider-state", category="Demo")
    db_session.add(product)
    db_session.flush()
    return create_generation_task(db_session, product.id, None, "minimal")


def test_image_provider_no_key_is_explicit(db_session, monkeypatch):
    task = _task(db_session)
    monkeypatch.setattr("app.services.image_service.settings.image_gen_api_base", "")
    monkeypatch.setattr("app.services.image_service.settings.image_gen_api_key", "")
    assert process_generation_task(db_session, task.id).status == "no_key"


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        (httpx.TimeoutException("timed out"), "timeout"),
        (RuntimeError("provider rejected request"), "failed"),
        (None, "field_missing"),
    ],
)
def test_image_provider_failures_have_explicit_statuses(
    db_session, monkeypatch, side_effect, expected
):
    task = _task(db_session)
    monkeypatch.setattr("app.services.image_service.settings.image_gen_api_base", "https://provider.test")
    monkeypatch.setattr("app.services.image_service.settings.image_gen_api_key", "test-key")
    monkeypatch.setattr("app.services.image_service.settings.image_provider", "qwen")
    if side_effect is None:
        monkeypatch.setattr("app.services.image_service._call_qwen_image", lambda _task: [])
    else:
        def raise_provider(_task):
            raise side_effect
        monkeypatch.setattr("app.services.image_service._call_qwen_image", raise_provider)
    assert process_generation_task(db_session, task.id).status == expected
