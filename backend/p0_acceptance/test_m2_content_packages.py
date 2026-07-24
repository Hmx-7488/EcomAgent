"""Milestone 2 acceptance: approved facts, immutable content versions and approval."""

from __future__ import annotations

from .helpers import (
    CONTENT_PACKAGES_PATH,
    AUDIT_EVENTS_PATH,
    PRODUCTS_PATH,
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


def _create_package(client, headers, product_id: int, payload=None):
    response = client.post(
        CONTENT_PACKAGES_PATH,
        headers=headers,
        json={"product_id": product_id, "payload": payload or {"title": "原始标题", "faq": []}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_content_package_requires_an_approved_product_fact(client):
    operator = _operator(client)
    product = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={"name": "未审批事实", "category": "Demo", "skus": [{"sku_name": "SKU", "price": 100}]},
    )
    assert product.status_code == 201
    response = client.post(
        CONTENT_PACKAGES_PATH,
        headers=operator,
        json={"product_id": product.json()["id"], "payload": {"title": "不得生成"}},
    )
    assert response.status_code == 409
    # The envelope is frozen; the domain code may be the more specific
    # ``approved_product_required`` rather than the generic ``conflict``.
    assert error_detail(response)["code"]


def test_content_package_captures_fact_source_and_never_overwrites_versions(client):
    operator = _operator(client)
    product = create_approved_product(client, operator)
    package = _create_package(client, operator, product["id"])
    assert package["status"] == "draft"
    assert package["source_fact_version"]
    assert package["source_summary"]
    assert len(package["versions"]) == 1
    original = package["versions"][0]

    changed = client.patch(
        f"{CONTENT_PACKAGES_PATH}/{package['id']}",
        headers=operator,
        json={"payload": {"title": "修订标题", "selling_points": ["仅来自事实"]}},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["current_version_no"] == 2
    assert len(body["versions"]) == 2
    assert body["versions"][0]["id"] == original["id"]
    assert body["versions"][0]["payload"] == original["payload"]
    assert body["versions"][-1]["payload"]["title"] == "修订标题"


def test_content_generation_records_provider_metadata_and_field_missing(client, monkeypatch):
    """C-F03/C-Q04: field-missing is visible and secrets are never persisted."""
    operator = _operator(client)
    product = create_approved_product(client, operator)
    package = _create_package(client, operator, product["id"])

    # M2 provider tests use the adapter stub, never a real model/network call.
    import app.services.content_service as content_service
    monkeypatch.setattr(content_service, "generate_package_with_provider", lambda *_args, **_kwargs: {"title": None})
    response = client.post(
        f"{CONTENT_PACKAGES_PATH}/{package['id']}/generate",
        headers=operator,
        json={"content_type": "title", "platform": "general"},
    )
    assert response.status_code == 200, response.text
    version = response.json()["versions"][-1]
    assert version["task_status"] == "field_missing"
    assert version["error_summary"]
    serialized = str(response.json()).lower()
    assert "test-key" not in serialized and "api_key" not in serialized


def test_content_approval_state_machine_rejection_reason_and_export_gate(client):
    operator = _operator(client)
    admin = _admin(client)
    product = create_approved_product(client, operator)
    package = _create_package(client, operator, product["id"])

    assert client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/export", headers=admin).status_code == 409
    assert client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/approve", headers=admin, json={}).status_code == 409
    assert client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/submit", headers=operator, json={}).status_code == 200
    rejected = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/reject", headers=admin, json={})
    assert rejected.status_code == 422
    assert error_detail(rejected)["code"]
    rejected = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/reject", headers=admin, json={"reason": "事实来源待补充"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # A rejected package becomes a new draft version when the operator edits it.
    draft = client.patch(f"{CONTENT_PACKAGES_PATH}/{package['id']}", headers=operator, json={"payload": {"title": "补充后重提"}})
    assert draft.status_code == 200
    assert draft.json()["status"] == "draft"
    assert client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/submit", headers=operator, json={}).status_code == 200
    approved = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/approve", headers=admin, json={})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    exported = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/export", headers=admin)
    assert exported.status_code == 200, exported.text
    assert exported.json()["package_id"] == package["id"]
    assert "markdown" in exported.json()

    audit = client.get(AUDIT_EVENTS_PATH, headers=admin)
    assert audit.status_code == 200, audit.text
    actions = {event["action"] for event in audit.json()["items"] if event["target_id"] == package["id"]}
    assert {"content.created", "content.edited", "content.submitted", "content.rejected", "content.approved", "content.exported"} <= actions


def test_content_is_denied_to_customer_service_and_anonymous(client):
    service = login_as(client, ROLE_CUSTOMER_SERVICE, TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE])
    for headers, expected in ((service, 403), ({"Authorization": ""}, 401)):
        response = client.get(CONTENT_PACKAGES_PATH, headers=headers)
        assert response.status_code == expected
        assert error_detail(response)["code"] in {"permission_denied", "authentication_required"}
