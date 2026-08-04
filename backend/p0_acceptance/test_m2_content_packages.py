"""Milestone 2 acceptance: approved facts, immutable content versions and approval."""

from __future__ import annotations

import json

import pytest

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


PACKAGE_FIELDS = (
    "title",
    "selling_points",
    "detail",
    "parameters",
    "faq",
    "sales_script",
    "promo_material",
)
COMPLETE_PACKAGE_PAYLOAD = {
    "title": "完整标题",
    "selling_points": "卖点一\n卖点二",
    "detail": "完整详情",
    "parameters": "尺寸：示例",
    "faq": "Q：示例问题\nA：示例回答",
    "sales_script": "售前话术",
    "promo_material": "推广素材",
}


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


def _configured_package_llm(monkeypatch, raw_response):
    """Run the package adapter with an in-process response and no network."""
    import app.services.llm_service as llm_service

    monkeypatch.setattr(llm_service.settings, "llm_provider", "qwen")
    monkeypatch.setattr(llm_service.settings, "llm_api_base", "https://provider.invalid")
    monkeypatch.setattr(llm_service.settings, "llm_api_key", "test-only")
    monkeypatch.setattr(llm_service.settings, "llm_model", "qwen-plus")
    calls = []

    def fake_response(messages, max_tokens=2048):
        calls.append((messages, max_tokens))
        return json.dumps(raw_response, ensure_ascii=False)

    monkeypatch.setattr(llm_service, "_get_llm_response", fake_response)
    result = llm_service.generate_product_content(
        product_name="Demo 商品",
        category="Demo 类目",
        brand="Demo 品牌",
        description="Demo 描述",
        selling_points="Demo 卖点",
        parameters_json='{"size":"demo"}',
        content_type="package",
        platform="general",
    )
    return result, calls


def test_complete_package_prompt_calls_provider_once_and_returns_only_formal_fields(monkeypatch):
    raw = {
        **{key: f"  {value}  " for key, value in COMPLETE_PACKAGE_PAYLOAD.items()},
        "short_title": "不得持久化",
        "product_name": "不得持久化",
        "category": "不得持久化",
        "brand": "不得持久化",
        "platform": "不得持久化",
        "provider_message": "不得持久化",
    }

    result, calls = _configured_package_llm(monkeypatch, raw)

    assert len(calls) == 1
    assert result == COMPLETE_PACKAGE_PAYLOAD
    prompt = calls[0][0][1]["content"]
    for field in PACKAGE_FIELDS:
        assert f'"{field}"' in prompt
    for legacy_field in ("short_title", "script", "keywords"):
        assert f'"{legacy_field}"' not in prompt


def test_complete_package_normalizes_a_valid_faq_array(monkeypatch):
    raw = {
        **COMPLETE_PACKAGE_PAYLOAD,
        "faq": [
            {"q": "  问题一？ ", "a": " 回答一。 "},
            {"q": "问题二？", "a": "回答二。"},
        ],
    }

    result, _ = _configured_package_llm(monkeypatch, raw)

    assert result["faq"] == "Q：问题一？\nA：回答一。\n\nQ：问题二？\nA：回答二。"


@pytest.mark.parametrize(
    "invalid_faq",
    [
        [],
        [{}],
        [{"q": "问题"}],
        [{"a": "回答"}],
        [{"q": " ", "a": "回答"}],
        [{"q": "问题", "a": " "}],
        [{"q": 1, "a": "回答"}],
        [{"q": "问题", "a": False}],
        {"q": "问题", "a": "回答"},
        1,
        True,
    ],
)
def test_complete_package_rejects_malformed_faq(monkeypatch, invalid_faq):
    import app.services.llm_service as llm_service

    with pytest.raises(ValueError, match="complete package"):
        _configured_package_llm(
            monkeypatch,
            {**COMPLETE_PACKAGE_PAYLOAD, "faq": invalid_faq},
        )


@pytest.mark.parametrize("raw_response", [[], [COMPLETE_PACKAGE_PAYLOAD], "not-an-object"])
def test_complete_package_rejects_non_object_json(monkeypatch, raw_response):
    with pytest.raises(ValueError, match="complete package"):
        _configured_package_llm(monkeypatch, raw_response)


def test_complete_package_generation_persists_one_exact_version_and_audit(
    client, monkeypatch, db_session
):
    import app.services.content_service as content_service
    from app.models.content import ApprovalRecord, AuditEvent, ContentVersion

    operator = _operator(client)
    product = create_approved_product(client, operator)
    package = _create_package(client, operator, product["id"])
    original_version = package["versions"][0]
    provider_calls = []

    def provider_stub(**kwargs):
        provider_calls.append(kwargs)
        return {
            **COMPLETE_PACKAGE_PAYLOAD,
            "short_title": "不得持久化",
            "api_key": "sensitive-sentinel",
            "provider_message": "sensitive-sentinel",
        }

    monkeypatch.setattr(content_service, "generate_package_with_provider", provider_stub)
    version_count_before = db_session.query(ContentVersion).count()
    audit_count_before = db_session.query(AuditEvent).filter(
        AuditEvent.action == "content.generated",
        AuditEvent.target_type == "content_package",
        AuditEvent.target_id == package["id"],
    ).count()

    response = client.post(
        f"{CONTENT_PACKAGES_PATH}/{package['id']}/generate",
        headers=operator,
        json={"package_id": package["id"], "content_type": "package", "platform": "general"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    latest = body["versions"][-1]
    assert len(provider_calls) == 1
    assert provider_calls[0]["content_type"] == "package"
    assert provider_calls[0]["platform"] == "general"
    assert latest["task_status"] == "completed"
    assert latest["error_summary"] is None
    assert latest["payload"] == COMPLETE_PACKAGE_PAYLOAD
    assert body["current_version_no"] == package["current_version_no"] + 1
    assert len(body["versions"]) == len(package["versions"]) + 1
    assert body["versions"][0] == original_version
    assert body["status"] == package["status"] == "draft"
    assert db_session.query(ContentVersion).count() == version_count_before + 1
    assert db_session.query(AuditEvent).filter(
        AuditEvent.action == "content.generated",
        AuditEvent.target_type == "content_package",
        AuditEvent.target_id == package["id"],
    ).count() == audit_count_before + 1
    assert db_session.query(ApprovalRecord).filter(
        ApprovalRecord.target_type == "content_package",
        ApprovalRecord.target_id == package["id"],
    ).count() == 0
    serialized = json.dumps(body, ensure_ascii=False)
    assert "sensitive-sentinel" not in serialized


def _invalid_package_payload(field: str, defect: str) -> dict:
    payload = dict(COMPLETE_PACKAGE_PAYLOAD)
    if defect == "missing":
        payload.pop(field)
    elif defect == "blank":
        payload[field] = " \t\r\n "
    else:
        payload[field] = {"invalid": True}
    return payload


@pytest.mark.parametrize("field", PACKAGE_FIELDS)
@pytest.mark.parametrize("defect", ["missing", "blank", "wrong_type"])
def test_complete_package_generation_rejects_each_invalid_field(
    client, monkeypatch, db_session, field, defect
):
    import app.services.content_service as content_service
    from app.models.content import AuditEvent, ContentVersion

    operator = _operator(client)
    product = create_approved_product(client, operator)
    package = _create_package(client, operator, product["id"])
    original_version = package["versions"][0]
    provider_calls = []
    monkeypatch.setattr(
        content_service,
        "generate_package_with_provider",
        lambda **_kwargs: provider_calls.append(1) or _invalid_package_payload(field, defect),
    )
    version_count_before = db_session.query(ContentVersion).count()
    audit_count_before = db_session.query(AuditEvent).filter(
        AuditEvent.action == "content.generated",
        AuditEvent.target_id == package["id"],
    ).count()

    response = client.post(
        f"{CONTENT_PACKAGES_PATH}/{package['id']}/generate",
        headers=operator,
        json={"package_id": package["id"], "content_type": "package", "platform": "general"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    latest = body["versions"][-1]
    assert len(provider_calls) == 1
    assert latest["task_status"] == "field_missing"
    assert latest["task_status"] != "completed"
    assert latest["error_summary"] == "Provider response has incomplete package content"
    assert latest["payload"] == {}
    assert len(body["versions"]) == len(package["versions"]) + 1
    assert body["versions"][0] == original_version
    assert body["status"] == package["status"] == "draft"
    assert db_session.query(ContentVersion).count() == version_count_before + 1
    assert db_session.query(AuditEvent).filter(
        AuditEvent.action == "content.generated",
        AuditEvent.target_id == package["id"],
    ).count() == audit_count_before + 1


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
