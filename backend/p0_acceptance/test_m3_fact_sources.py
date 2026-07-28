"""M3 acceptance: fact tools read only approved facts and approved FAQ versions."""

from __future__ import annotations

import json
from datetime import timedelta

from .helpers import (
    AUDIT_EVENTS_PATH,
    CONTENT_PACKAGES_PATH,
    PRODUCTS_PATH,
    ROLE_ADMIN,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    ask_customer,
    create_customer_conversation,
    login_as,
)


def _product_without_usage_fact(client, operator, name):
    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": name,
            "category": "Demo",
            "parameters_json": "{}",
            "skus": [{"sku_name": "standard", "price": 10}],
        },
    )
    assert created.status_code == 201, created.text
    approved = client.put(
        f"{PRODUCTS_PATH}/{created.json()['id']}",
        headers=operator,
        json={"status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def _faq_package(client, operator, product_id, question, answer):
    package = client.post(
        CONTENT_PACKAGES_PATH,
        headers=operator,
        json={
            "product_id": product_id,
            "payload": {"faq": [{"question": question, "answer": answer}]},
        },
    )
    assert package.status_code == 201, package.text
    return package.json()


def test_only_approved_faq_is_answered_and_source_version_is_recorded(client):
    operator = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    admin = login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])
    question = "\u8fd9\u4e2a\u5546\u54c1\u600e\u4e48\u7528\uff1f"
    answer = "\u8bf7\u6309\u5df2\u5ba1\u6838\u8bf4\u660e\u4e66\u5b89\u88c5\u540e\u4f7f\u7528\u3002"
    product = _product_without_usage_fact(client, operator, "M3 approved FAQ")
    package = _faq_package(client, operator, product["id"], question, answer)
    submitted = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/submit", headers=operator, json={})
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/approve", headers=admin, json={})
    assert approved.status_code == 200, approved.text

    result = ask_customer(client, create_customer_conversation(client, product["id"]), question)
    assert result["decision"] == "auto_reply"
    assert result["reply"]["content"] == answer
    assert result["source_summary"][0]["source_type"] == "content_version"
    assert result["source_summary"][0]["source_object_id"]
    assert result["source_summary"][0]["source_version"]
    assert result["source_summary"][0]["data_time"]


def test_draft_faq_is_never_used_as_customer_fact(client):
    operator = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    question = "\u8fd9\u4e2a\u5546\u54c1\u600e\u4e48\u7528\uff1f"
    product = _product_without_usage_fact(client, operator, "M3 draft FAQ")
    _faq_package(
        client,
        operator,
        product["id"],
        question,
        "\u672a\u5ba1\u6279\u7684\u7b54\u6848\u4e0d\u5f97\u4f7f\u7528\u3002",
    )
    result = ask_customer(client, create_customer_conversation(client, product["id"]), question)
    assert result["decision"] == "transfer"
    assert result["reason_code"] == "fact_missing_or_ambiguous"
    assert result["reply"] is None
    assert result["source_summary"] == []

def test_approved_faq_becomes_stale_after_product_fact_version_changes(client, db_session):
    operator = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    admin = login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])
    question = "\u8fd9\u4e2a\u5546\u54c1\u600e\u4e48\u7528\uff1f"
    answer = "\u8fd9\u662f\u4e0e\u5f53\u524d\u5546\u54c1\u4e8b\u5b9e\u7248\u672c\u4e00\u81f4\u7684 FAQ\u3002"
    product = _product_without_usage_fact(client, operator, "M3 stale FAQ")
    package = _faq_package(client, operator, product["id"], question, answer)
    assert package["source_fact_version"]
    submitted = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/submit", headers=operator, json={})
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"{CONTENT_PACKAGES_PATH}/{package['id']}/approve", headers=admin, json={})
    assert approved.status_code == 200, approved.text

    conversation = create_customer_conversation(client, product["id"])
    current = ask_customer(client, conversation, question)
    assert current["decision"] == "auto_reply"
    assert current["reply"]["content"] == answer

    from app.models.product import Product

    stored = db_session.get(Product, product["id"])
    stored.updated_at = stored.updated_at + timedelta(days=1)
    db_session.commit()

    stale = ask_customer(client, conversation, question)
    assert stale["decision"] == "transfer"
    assert stale["reason_code"] == "fact_missing_or_ambiguous"
    assert stale["reply"] is None
    assert stale["source_summary"] == []
    assert stale["notice"]["content"] == "\u5df2\u8f6c\u4eba\u5de5\uff0c\u8bf7\u7b49\u5f85\u5ba2\u670d\u5904\u7406"

    response = client.get(AUDIT_EVENTS_PATH, headers=admin)
    assert response.status_code == 200, response.text
    fact_events = [
        event
        for event in response.json()["items"]
        if event["target_id"] == conversation["id"] and event["action"] == "fact.queried"
    ]
    evidence = [json.loads(event["after_json"]) for event in fact_events]
    assert any(item["source_count"] > 0 and item["fact_status"] == "complete" for item in evidence)
    assert any(item["source_count"] == 0 and item["fact_status"] == "missing" for item in evidence)
