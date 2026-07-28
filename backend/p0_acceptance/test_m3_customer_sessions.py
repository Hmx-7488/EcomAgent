"""M3 acceptance: anonymous customer visibility and bearer-token isolation."""

from __future__ import annotations

import json

from .helpers import (
    AUDIT_EVENTS_PATH,
    CUSTOMER_CONVERSATIONS_PATH,
    CUSTOMER_PRODUCTS_PATH,
    PRODUCTS_PATH,
    ROLE_ADMIN,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    ask_customer,
    create_approved_demo_product,
    create_customer_conversation,
    customer_headers,
    error_detail,
    login_as,
)


def _operator(client):
    return login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])


def _admin(client):
    return login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])


def test_customer_catalog_exposes_only_approved_sanitized_facts(client):
    operator = _operator(client)
    approved = create_approved_demo_product(client, operator)
    draft = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": "\u4e0d\u53ef\u89c1\u8349\u7a3f",
            "category": "Demo",
            "skus": [{"sku_name": "\u8349\u7a3f", "price": 1}],
        },
    )
    assert draft.status_code == 201

    response = client.get(CUSTOMER_PRODUCTS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == approved["id"]
    assert payload["items"][0]["status"] == "approved"
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ("price", "stock", "inventory", "cost", "margin", "audit"):
        assert forbidden not in serialized


def test_anonymous_session_token_is_one_time_and_isolated(client, db_session, caplog):
    product = create_approved_demo_product(client, _operator(client))
    first = create_customer_conversation(client, product["id"])
    second = create_customer_conversation(client, product["id"])
    assert first["access_token"] != second["access_token"]

    own = client.get(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{first['id']}",
        headers=customer_headers(first["access_token"]),
    )
    assert own.status_code == 200, own.text
    assert "access_token" not in own.json()

    cross = client.get(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{first['id']}",
        headers=customer_headers(second["access_token"]),
    )
    missing = client.get(
        f"{CUSTOMER_CONVERSATIONS_PATH}/999999999",
        headers=customer_headers(second["access_token"]),
    )
    assert cross.status_code == missing.status_code
    assert error_detail(cross)["code"] == error_detail(missing)["code"]

    # Storage, responses, audit output and logs may contain only a digest.
    from app.models.content import Conversation

    persisted = db_session.get(Conversation, first["id"])
    assert first["access_token"] not in repr(vars(persisted))
    audit = client.get(AUDIT_EVENTS_PATH, headers=_admin(client))
    assert audit.status_code == 200, audit.text
    evidence = own.text + audit.text + caplog.text + repr(vars(persisted))
    assert first["access_token"] not in evidence


def test_unapproved_product_cannot_start_customer_conversation(client):
    operator = _operator(client)
    draft = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": "\u672a\u6279\u51c6\u5546\u54c1",
            "category": "Demo",
            "skus": [{"sku_name": "\u8349\u7a3f", "price": 1}],
        },
    )
    assert draft.status_code == 201
    response = client.post(CUSTOMER_CONVERSATIONS_PATH, json={"product_id": draft.json()["id"]})
    assert response.status_code in {404, 409}
    assert error_detail(response)["code"] in {
        "not_found",
        "approved_product_required",
        "conflict",
    }


def test_product_losing_approval_mid_session_fails_closed(client):
    operator = _operator(client)
    product = create_approved_demo_product(client, operator)
    conversation = create_customer_conversation(client, product["id"])
    changed = client.put(
        f"{PRODUCTS_PATH}/{product['id']}",
        headers=operator,
        json={"status": "active"},
    )
    assert changed.status_code == 200, changed.text
    response = client.post(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{conversation['id']}/messages",
        headers=customer_headers(conversation["access_token"]),
        json={"content": "\u5546\u54c1\u662f\u4ec0\u4e48\u6750\u8d28\uff1f"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "transfer"
    assert result["reason_code"] == "approved_product_required"
    assert result["reply"] is None

def test_customer_refresh_exposes_only_latest_safe_reason_code(client):
    product = create_approved_demo_product(client, _operator(client), "ZN-DB-002")
    conversation = create_customer_conversation(client, product["id"])
    assert conversation["reason_code"] is None

    result = ask_customer(
        client,
        conversation,
        "\u8010\u70ed\u6e29\u5ea6\u662f\u591a\u5c11\uff1f",
    )
    assert result["decision"] == "transfer"
    refreshed = client.get(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{conversation['id']}",
        headers=customer_headers(conversation["access_token"]),
    )
    assert refreshed.status_code == 200, refreshed.text
    payload = refreshed.json()
    assert payload["reason_code"] == result["reason_code"]
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for internal in ("review_draft", "pending_draft", "source_summary", "fact_sources", "decisions"):
        assert internal not in serialized
