"""M3 acceptance: service review queues, RBAC, state changes and audit evidence."""

from __future__ import annotations

import json

from .helpers import (
    AUDIT_EVENTS_PATH,
    CUSTOMER_CONVERSATIONS_PATH,
    ROLE_ADMIN,
    ROLE_CUSTOMER_SERVICE,
    ROLE_OPERATOR_CONTENT,
    SERVICE_CONVERSATIONS_PATH,
    TEST_PASSWORDS,
    ask_customer,
    create_approved_demo_product,
    create_customer_conversation,
    customer_headers,
    error_detail,
    load_demo_json,
    login_as,
)


GOLD = {
    item["id"]: item
    for filename in ("qa_gold.json", "qa_gold_addendum.json")
    for item in load_demo_json(filename)
}


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


def _login(client, role):
    return login_as(client, role, TEST_PASSWORDS[role])


def _waiting_review(client):
    _use_success_provider()
    product = create_approved_demo_product(client, _login(client, ROLE_OPERATOR_CONTENT))
    conversation = create_customer_conversation(client, product["id"])
    result = ask_customer(client, conversation, GOLD["QA-02"]["question"])
    assert result["status"] == "waiting_review"
    assert result["decision"] == "review_draft"
    assert result["reply"] is None
    return conversation


def test_customer_service_can_edit_and_send_but_operator_cannot_access_queue(client):
    conversation = _waiting_review(client)
    service = _login(client, ROLE_CUSTOMER_SERVICE)
    operator = _login(client, ROLE_OPERATOR_CONTENT)

    for path in (SERVICE_CONVERSATIONS_PATH, f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}"):
        denied = client.get(path, headers=operator)
        assert denied.status_code == 403
        assert error_detail(denied)["code"] == "permission_denied"
    for anonymous_headers in (
        {"Authorization": ""},
        {"Authorization": "", "X-Conversation-Token": conversation["access_token"]},
    ):
        denied = client.get(SERVICE_CONVERSATIONS_PATH, headers=anonymous_headers)
        assert denied.status_code == 401
        assert error_detail(denied)["code"] == "authentication_required"

    invalid_queue = client.get(f"{SERVICE_CONVERSATIONS_PATH}?status=open", headers=service)
    assert invalid_queue.status_code == 422
    assert error_detail(invalid_queue)["code"] == "validation_error"

    queue = client.get(f"{SERVICE_CONVERSATIONS_PATH}?status=waiting_review", headers=service)
    assert queue.status_code == 200, queue.text
    assert [item["id"] for item in queue.json()["items"]] == [conversation["id"]]

    before = client.get(f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}", headers=service)
    assert before.status_code == 200, before.text
    detail = before.json()
    original = detail["pending_draft"]
    assert original and original["content"]
    assert not any(
        message["visible_to_customer"]
        for message in detail["messages"]
        if message["message_type"] == "review_draft"
    )

    edited_content = "\u5df2\u4eba\u5de5\u6838\u5bf9\uff1a\u4ef7\u683c\u4e3a Demo \u9759\u6001\u8d44\u6599\uff0c\u4e0d\u4ee3\u8868\u5b9e\u65f6\u552e\u4ef7\u3002"
    sent = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}/send",
        headers=service,
        json={"content": edited_content},
    )
    assert sent.status_code == 200, sent.text
    after = sent.json()
    assert after["status"] == "open"
    assert after["pending_draft"] is None
    assert any(
        message["message_type"] == "review_draft" and message["content"] == original["content"]
        for message in after["messages"]
    )
    staff = next(message for message in after["messages"] if message["message_type"] == "staff_reply")
    assert staff["content"] == edited_content
    assert staff["actor_id"]
    assert staff["created_at"]

    customer_view = client.get(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{conversation['id']}",
        headers=customer_headers(conversation["access_token"]),
    )
    assert customer_view.status_code == 200
    visible = customer_view.json()["messages"]
    assert any(message["content"] == edited_content for message in visible)
    assert original["content"] not in [message["content"] for message in visible]

    audit = client.get(AUDIT_EVENTS_PATH, headers=_login(client, ROLE_ADMIN))
    assert audit.status_code == 200
    actions = {
        event["action"]
        for event in audit.json()["items"]
        if event["target_id"] == conversation["id"]
    }
    assert {
        "draft.generated",
        "draft.edited",
        "reply.agent_sent",
        "conversation.status_changed",
    } <= actions


def test_service_manual_transfer_and_resolve_are_audited(client):
    conversation = _waiting_review(client)
    admin = _login(client, ROLE_ADMIN)
    reason = "\u987e\u5ba2\u8bf7\u6c42\u4eba\u5de5\u8fdb\u4e00\u6b65\u6838\u5b9e"
    transferred = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}/transfer",
        headers=admin,
        json={"reason": reason},
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["status"] == "transferred"
    assert transferred.json()["transfer_reason"] == reason

    queue = client.get(f"{SERVICE_CONVERSATIONS_PATH}?status=transferred", headers=admin)
    assert queue.status_code == 200
    assert conversation["id"] in [item["id"] for item in queue.json()["items"]]

    resolved = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}/resolve",
        headers=admin,
        json={},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    customer_blocked = client.post(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{conversation['id']}/messages",
        headers=customer_headers(conversation["access_token"]),
        json={"content": "\u7ee7\u7eed\u63d0\u95ee"},
    )
    assert customer_blocked.status_code == 409
    assert error_detail(customer_blocked)["code"] == "conversation_resolved"
    send_blocked = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}/send",
        headers=admin,
        json={"content": "not allowed"},
    )
    assert send_blocked.status_code == 409

    audit = client.get(AUDIT_EVENTS_PATH, headers=admin)
    relevant = [
        event
        for event in audit.json()["items"]
        if event["target_id"] == conversation["id"]
    ]
    assert any(event["action"] == "conversation.transferred" for event in relevant)
    status_events = [event for event in relevant if event["action"] == "conversation.status_changed"]
    assert any("resolved" in (event.get("summary") or "").lower() for event in status_events)
    manual_status_events = [event for event in status_events if event["actor_id"] == 1]
    assert len(manual_status_events) >= 2


def test_service_detail_contains_safe_sources_but_no_financial_or_inventory_fields(client):
    product = create_approved_demo_product(client, _login(client, ROLE_OPERATOR_CONTENT), "ZN-DB-002")
    conversation = create_customer_conversation(client, product["id"])
    result = ask_customer(client, conversation, GOLD["QA-31"]["question"])
    assert result["decision"] == "auto_reply"

    admin = _login(client, ROLE_ADMIN)
    detail = client.get(f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}", headers=admin)
    assert detail.status_code == 200, detail.text
    source = detail.json()["decisions"][-1]["fact_sources"][0]
    assert source["source_object_id"]
    assert source["source_version"]
    assert source["field_summary"]
    assert source["data_time"]
    audit = client.get(AUDIT_EVENTS_PATH, headers=admin)
    assert audit.status_code == 200, audit.text
    actions = {
        event["action"]
        for event in audit.json()["items"]
        if event["target_id"] == conversation["id"]
    }
    assert {"conversation.created", "risk.assessed", "fact.queried", "reply.auto_sent"} <= actions
    serialized = json.dumps(detail.json(), ensure_ascii=False).lower()
    for forbidden in (
        "purchase_cost",
        "packaging_cost",
        "shipping_subsidy",
        "platform_fee",
        "marketing_allocation",
        "promotion_allocation",
        "after_sales_loss",
        "margin",
        "inventory",
        "stock_quantity",
    ):
        assert forbidden not in serialized
