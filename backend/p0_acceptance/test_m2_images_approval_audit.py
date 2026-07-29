"""Milestone 2 acceptance: reference-image gate, image approval, export and audit."""

from __future__ import annotations

import io

import pytest

from scripts.image_fixture import png_bytes

from .helpers import (
    AUDIT_EVENTS_PATH,
    IMAGE_REFERENCE_PATH,
    IMAGE_TASKS_PATH,
    ROLE_ADMIN,
    ROLE_CUSTOMER_SERVICE,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    create_approved_product,
    error_detail,
    login_as,
)


def _operator(client):
    return login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])


def _admin(client):
    return login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])


def _reference(client, headers, product_id: int):
    response = client.post(
        IMAGE_REFERENCE_PATH,
        headers=headers,
        data={"product_id": str(product_id)},
        files={"file": ("reference.png", io.BytesIO(png_bytes()), "image/png")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["asset_type"] == "reference"
    return response.json()


def _task(client, headers, product_id: int, reference_id: int):
    response = client.post(
        IMAGE_TASKS_PATH,
        headers=headers,
        json={"product_id": product_id, "style": "minimal", "reference_asset_id": reference_id},
    )
    assert response.status_code == 202, response.text
    return response.json()["task_id"]


def test_image_task_requires_reference_image(client):
    operator = _operator(client)
    product = create_approved_product(client, operator)
    response = client.post(IMAGE_TASKS_PATH, headers=operator, json={"product_id": product["id"], "style": "minimal"})
    assert response.status_code == 422
    assert error_detail(response)["code"]


def test_image_provider_no_key_timeout_failed_and_field_missing_are_explicit(client, monkeypatch):
    """Provider outcomes are deterministic under test and use no network."""
    operator = _operator(client)
    product = create_approved_product(client, operator)
    reference = _reference(client, operator, product["id"])
    import app.services.image_service as image_service

    outcomes = [
        ("no_key", lambda *_args, **_kwargs: (_ for _ in ()).throw(image_service.ProviderNoKeyError("missing"))),
        ("timeout", lambda *_args, **_kwargs: (_ for _ in ()).throw(image_service.ProviderTimeoutError("slow"))),
        ("failed", lambda *_args, **_kwargs: (_ for _ in ()).throw(image_service.ProviderFailedError("rejected"))),
        ("field_missing", lambda *_args, **_kwargs: {"images": []}),
    ]
    for expected, fake_provider in outcomes:
        monkeypatch.setattr(image_service, "generate_image_with_provider", fake_provider)
        task_id = _task(client, operator, product["id"], reference["id"])
        detail = client.get(f"{IMAGE_TASKS_PATH}/{task_id}", headers=operator)
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == expected
        assert detail.json().get("error_message") or expected == "field_missing"


def test_failed_image_can_retry_but_unconfirmed_or_unapproved_assets_cannot_export(client, monkeypatch):
    operator = _operator(client)
    admin = _admin(client)
    product = create_approved_product(client, operator)
    reference = _reference(client, operator, product["id"])
    import app.services.image_service as image_service
    monkeypatch.setattr(image_service, "generate_image_with_provider", lambda *_args, **_kwargs: (_ for _ in ()).throw(image_service.ProviderFailedError("temporary")))
    task_id = _task(client, operator, product["id"], reference["id"])
    assert client.post(f"{IMAGE_TASKS_PATH}/{task_id}/retry", headers=operator, json={}).status_code == 200
    assert client.post(f"{IMAGE_TASKS_PATH}/{task_id}/export", headers=admin).status_code == 409


def test_image_approval_requires_completed_confirmed_submitted_task_and_records_audit(client, monkeypatch):
    operator = _operator(client)
    admin = _admin(client)
    product = create_approved_product(client, operator)
    reference = _reference(client, operator, product["id"])
    import app.services.image_service as image_service
    monkeypatch.setattr(image_service, "generate_image_with_provider", lambda **_: {"images": [png_bytes(width=12, height=10)]})
    task_id = _task(client, operator, product["id"], reference["id"])

    assert client.post(f"{IMAGE_TASKS_PATH}/{task_id}/export", headers=admin).status_code == 409
    assert client.post(f"{IMAGE_TASKS_PATH}/{task_id}/confirm", headers=operator, json={}).status_code == 200
    assert client.post(f"{IMAGE_TASKS_PATH}/{task_id}/submit", headers=operator, json={}).status_code == 200
    rejected = client.post(f"{IMAGE_TASKS_PATH}/{task_id}/reject", headers=admin, json={})
    assert rejected.status_code == 422
    assert error_detail(rejected)["code"]
    assert client.post(f"{IMAGE_TASKS_PATH}/{task_id}/approve", headers=admin, json={}).status_code == 200
    exported = client.post(f"{IMAGE_TASKS_PATH}/{task_id}/export", headers=admin)
    assert exported.status_code == 200, exported.text
    assert exported.json()["task_id"] == task_id

    audit = client.get(AUDIT_EVENTS_PATH, headers=admin)
    assert audit.status_code == 200, audit.text
    actions = {event["action"] for event in audit.json()["items"] if event["target_id"] == task_id}
    assert {"image.created", "image.confirmed", "image.submitted", "image.approved", "image.exported"} <= actions


@pytest.mark.parametrize("path", [IMAGE_REFERENCE_PATH, IMAGE_TASKS_PATH, AUDIT_EVENTS_PATH])
def test_images_and_audit_are_denied_to_customer_service_and_anonymous(client, path):
    service = login_as(client, ROLE_CUSTOMER_SERVICE, TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE])
    for headers, expected in ((service, 403), ({"Authorization": ""}, 401)):
        response = client.get(path, headers=headers)
        assert response.status_code == expected
        assert error_detail(response)["code"] in {"permission_denied", "authentication_required"}
