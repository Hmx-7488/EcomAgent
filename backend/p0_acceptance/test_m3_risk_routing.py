"""M3 acceptance: deterministic risk rules precede generation and fail closed."""

from __future__ import annotations

import json

import pytest

from .helpers import (
    AUDIT_EVENTS_PATH,
    PRODUCTS_PATH,
    ROLE_ADMIN,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    ask_customer,
    create_approved_demo_product,
    create_customer_conversation,
    load_demo_json,
    login_as,
)


def _assert_zero_source_fact_query(client, conversation_id):
    admin = login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])
    response = client.get(AUDIT_EVENTS_PATH, headers=admin)
    assert response.status_code == 200, response.text
    fact_events = [
        event
        for event in response.json()["items"]
        if event["target_id"] == conversation_id and event["action"] == "fact.queried"
    ]
    assert len(fact_events) == 1
    evidence = json.loads(fact_events[0]["after_json"])
    assert evidence["source_count"] == 0
    assert evidence["fact_status"] in {"missing", "conflict"}
def _operator(client):
    return login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])


def _by_id(*filenames):
    return {
        item["id"]: item
        for filename in filenames
        for item in load_demo_json(filename)
    }


GOLD = _by_id("qa_gold.json", "qa_gold_addendum.json")
RED_TEAM = _by_id("red_team.json", "red_team_addendum.json")

class SuccessfulDraftProvider:
    name = "acceptance_success_stub"

    def reply(self, _fact_text):
        raise AssertionError("low-risk deterministic replies must not call Provider")

    def draft(self, _question, _safe_fact_summary):
        return "internal review draft"


def _use_success_provider():
    from app.main import app
    from app.services.customer_service import get_customer_reply_provider

    provider = SuccessfulDraftProvider()
    app.dependency_overrides[get_customer_reply_provider] = lambda: provider
    return provider


LOW_RISK_CASES = (
    ("ZN-SB-001", "QA-01"),  # size
    ("ZN-SB-001", "QA-21"),  # capacity
    ("ZN-DB-002", "QA-31"),  # material
    ("ZN-SB-001", "QA-23"),  # color
    ("ZN-SB-001", "QA-29"),  # package
    ("ZN-VB-003", "QA-44"),  # usage
    ("ZN-VB-003", "QA-50"),  # applicable scene
)


@pytest.mark.parametrize(("product_code", "case_id"), LOW_RISK_CASES)
def test_complete_allowlisted_fact_auto_replies_with_traceable_source(client, product_code, case_id):
    product = create_approved_demo_product(client, _operator(client), product_code)
    result = ask_customer(
        client,
        create_customer_conversation(client, product["id"]),
        GOLD[case_id]["question"],
    )
    assert result["risk_level"] == "low"
    assert result["decision"] == "auto_reply"
    assert result["status"] == "open"
    assert result["reply"]
    assert result["notice"] is None
    assert result["source_summary"]
    for source in result["source_summary"]:
        assert source["source_object_id"]
        assert source["source_version"]
        assert source["field_summary"]
        assert source["data_time"]


@pytest.mark.parametrize(
    ("case_id", "reason_code"),
    (
        ("QA-02", "price_or_inventory"),
        ("QA-19", "price_or_inventory"),
        ("QA-15", "promotion"),
    ),
)
def test_medium_risk_creates_hidden_review_draft_and_never_auto_sends(client, case_id, reason_code):
    _use_success_provider()
    case = GOLD[case_id]
    product = create_approved_demo_product(client, _operator(client), case["product"])
    result = ask_customer(
        client,
        create_customer_conversation(client, product["id"]),
        case["question"],
    )
    assert result["risk_level"] == "medium"
    assert result["decision"] == "review_draft"
    assert result["status"] == "waiting_review"
    assert result["reply"] is None
    assert "draft" not in result
    assert result["reason_code"] == reason_code


@pytest.mark.parametrize("case_id", ("QA-03", "QA-20"))
def test_delivery_or_return_request_is_never_auto_replied(client, case_id):
    case = GOLD[case_id]
    product = create_approved_demo_product(client, _operator(client), case["product"])
    result = ask_customer(
        client,
        create_customer_conversation(client, product["id"]),
        case["question"],
    )
    assert result["risk_level"] in {"medium", "high"}
    assert result["decision"] in {"review_draft", "transfer"}
    assert result["status"] in {"waiting_review", "transferred"}
    assert result["reply"] is None


@pytest.mark.parametrize(
    "question",
    (
        "\u4f60\u4eec\u4ea7\u54c1\u8d28\u91cf\u592a\u5dee\u4e86\uff0c\u6211\u8981\u6295\u8bc9\uff01",
        RED_TEAM["RT-11"]["prompt"],
        "\u9a6c\u4e0a\u8f6c\u4eba\u5de5\uff0c\u4e0d\u8981\u673a\u5668\u4eba\u56de\u7b54\u3002",
        RED_TEAM["RT-30"]["prompt"],
    ),
)
def test_high_risk_transfers_without_response_time_commitment(client, question):
    product = create_approved_demo_product(client, _operator(client))
    result = ask_customer(client, create_customer_conversation(client, product["id"]), question)
    assert result["risk_level"] == "high"
    assert result["decision"] == "transfer"
    assert result["status"] == "transferred"
    assert result["reply"] is None
    assert result["notice"]["content"] == "\u5df2\u8f6c\u4eba\u5de5\uff0c\u8bf7\u7b49\u5f85\u5ba2\u670d\u5904\u7406"
    assert not any(
        term in result["notice"]["content"]
        for term in ("\u5206\u949f", "\u5c0f\u65f6", "\u9a6c\u4e0a", "\u7acb\u5373")
    )


def test_missing_fact_is_not_invented_and_transfers(client):
    operator = _operator(client)
    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": "M3 missing material",
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
    result = ask_customer(
        client,
        create_customer_conversation(client, approved.json()["id"]),
        GOLD["QA-31"]["question"],
    )
    assert result["decision"] == "transfer"
    assert result["status"] == "transferred"
    assert result["reply"] is None
    assert result["reason_code"] == "fact_missing_or_ambiguous"
    assert result["source_summary"] == []
    assert result["notice"]["content"] == "\u5df2\u8f6c\u4eba\u5de5\uff0c\u8bf7\u7b49\u5f85\u5ba2\u670d\u5904\u7406"
    _assert_zero_source_fact_query(client, result["conversation_id"])

def test_conflicting_fact_is_not_auto_replied(client):
    operator = _operator(client)
    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": "\u51b2\u7a81\u4e8b\u5b9e\u5546\u54c1",
            "category": "Demo",
            "description": "\u5546\u54c1\u6750\u8d28\u4e3a PVC",
            "parameters_json": json.dumps(
                {"material": "PP", "package": "\u5355\u4e2a\u88c5"}, ensure_ascii=False
            ),
            "skus": [{"sku_name": "\u6807\u51c6\u6b3e", "price": 10}],
        },
    )
    assert created.status_code == 201, created.text
    approved = client.put(
        f"{PRODUCTS_PATH}/{created.json()['id']}", headers=operator, json={"status": "approved"}
    )
    assert approved.status_code == 200
    result = ask_customer(
        client,
        create_customer_conversation(client, approved.json()["id"]),
        GOLD["QA-31"]["question"],
    )
    assert result["decision"] == "transfer"
    assert result["reply"] is None
    assert result["reason_code"] in {"fact_missing_or_ambiguous", "fact_conflict"}
    assert result["source_summary"] == []
    assert result["notice"]["content"] == "\u5df2\u8f6c\u4eba\u5de5\uff0c\u8bf7\u7b49\u5f85\u5ba2\u670d\u5904\u7406"
    _assert_zero_source_fact_query(client, result["conversation_id"])


@pytest.mark.parametrize(
    ("product_code", "question"),
    (
        (GOLD["QA-02"]["product"], GOLD["QA-02"]["question"]),
        ("ZN-SB-001", RED_TEAM["RT-11"]["prompt"]),
    ),
)
def test_medium_and_high_rules_short_circuit_before_fact_query(client, product_code, question):
    product = create_approved_demo_product(client, _operator(client), product_code)
    result = ask_customer(client, create_customer_conversation(client, product["id"]), question)
    assert result["decision"] in {"review_draft", "transfer"}
    admin = login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])
    response = client.get(AUDIT_EVENTS_PATH, headers=admin)
    assert response.status_code == 200, response.text
    actions = {
        event["action"]
        for event in response.json()["items"]
        if event["target_id"] == result["conversation_id"]
    }
    assert "risk.assessed" in actions
    assert "fact.queried" not in actions
