"""M3 acceptance: provider isolation and deterministic low-risk replies."""

from __future__ import annotations

import json

import pytest

from .helpers import (
    AUDIT_EVENTS_PATH,
    ROLE_ADMIN,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    ask_customer,
    create_approved_demo_product,
    create_customer_conversation,
    load_demo_json,
    login_as,
)


GOLD = {
    item["id"]: item
    for filename in ("qa_gold.json", "qa_gold_addendum.json")
    for item in load_demo_json(filename)
}


class FailingProvider:
    name = "acceptance_stub"

    def __init__(self, mode):
        self.mode = mode
        self.calls = 0
        self.inputs = []

    def _result(self):
        import app.services.customer_service as service

        errors = {
            "no_key": service.ProviderNoKeyError,
            "timeout": service.ProviderTimeoutError,
            "failed": service.ProviderFailedError,
            "field_missing": service.ProviderFieldMissingError,
        }
        raise errors[self.mode](self.mode)

    def reply(self, fact_text):
        self.calls += 1
        self.inputs.append(("reply", fact_text))
        return self._result()

    def draft(self, question, safe_fact_summary):
        self.calls += 1
        self.inputs.append(("draft", question, safe_fact_summary))
        return self._result()


def _override_provider(provider):
    from app.main import app
    from app.services.customer_service import get_customer_reply_provider

    app.dependency_overrides[get_customer_reply_provider] = lambda: provider


def _product(client, code="ZN-SB-001"):
    operator = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    return create_approved_demo_product(client, operator, code)


def _audit_for(client, conversation_id):
    admin = login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])
    response = client.get(AUDIT_EVENTS_PATH, headers=admin)
    assert response.status_code == 200, response.text
    return [
        event
        for event in response.json()["items"]
        if event["target_id"] == conversation_id
    ]


def test_low_risk_deterministic_template_does_not_call_provider_and_keeps_sources(client):
    provider = FailingProvider("failed")
    _override_provider(provider)
    conversation = create_customer_conversation(client, _product(client, "ZN-DB-002")["id"])
    result = ask_customer(client, conversation, GOLD["QA-31"]["question"])

    assert result["risk_level"] == "low"
    assert result["decision"] == "auto_reply"
    assert result["reply"] is not None
    assert provider.calls == 0
    assert result["source_summary"]
    assert all(source["source_object_id"] for source in result["source_summary"])

    events = _audit_for(client, result["conversation_id"])
    assert not any(event["action"] == "provider.degraded" for event in events)
    fact_event = next(event for event in events if event["action"] == "fact.queried")
    fact_after = json.loads(fact_event["after_json"])
    assert fact_after["fact_status"] == "complete"
    assert fact_after["source_count"] == len(result["source_summary"])


def test_default_qwen_without_key_fails_closed_before_any_network_call(client):
    from app.services.customer_service import get_customer_reply_provider

    provider = get_customer_reply_provider()
    assert provider.name == "qwen"
    conversation = create_customer_conversation(client, _product(client)["id"])
    result = ask_customer(client, conversation, GOLD["QA-02"]["question"])
    assert result["decision"] == "transfer"
    assert result["status"] == "transferred"
    assert result["reason_code"] == "provider_no_key"
    assert result["reply"] is None


@pytest.mark.parametrize("provider_state", ("no_key", "timeout", "failed", "field_missing"))
def test_medium_risk_provider_failure_transfers_once_without_visible_draft(client, provider_state):
    provider = FailingProvider(provider_state)
    _override_provider(provider)
    conversation = create_customer_conversation(client, _product(client)["id"])
    result = ask_customer(client, conversation, GOLD["QA-02"]["question"])

    assert result["risk_level"] == "high"
    assert result["decision"] == "transfer"
    assert result["status"] == "transferred"
    assert result["reason_code"] == f"provider_{provider_state}"
    assert result["reply"] is None
    assert provider.calls == 1
    assert provider.inputs[0][0] == "draft"
    safe_payload = provider.inputs[0][2].lower()
    assert "parameters" in safe_payload
    for forbidden in (
        "purchase_cost",
        "packaging_cost",
        "shipping_subsidy",
        "platform_fee",
        "marketing_allocation",
        "after_sales_loss",
        "margin",
        "inventory",
        "stock_quantity",
        "api_key",
        "access_token",
    ):
        assert forbidden not in safe_payload

    events = _audit_for(client, result["conversation_id"])
    assert any(event["action"] == "provider.degraded" for event in events)
    assert not any(event["action"] == "draft.generated" for event in events)
    serialized = json.dumps(events, ensure_ascii=False).lower()
    assert "api_key" not in serialized
    assert "access_token" not in serialized
