"""Gate 3 red tests for state, provider, input, and audit contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

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
    login_as,
)


class CountingProvider:
    name = "counting_stub"

    def __init__(self):
        self.reply_calls = 0
        self.draft_calls = 0
        self.draft_inputs = []

    @property
    def total_calls(self):
        return self.reply_calls + self.draft_calls

    def reply(self, fact_text):
        self.reply_calls += 1
        return fact_text

    def draft(self, question, safe_fact_summary):
        self.draft_calls += 1
        self.draft_inputs.append((question, safe_fact_summary))
        return "internal review draft"


def _login(client, role):
    return login_as(client, role, TEST_PASSWORDS[role])


def _use_provider(provider):
    from app.main import app
    from app.services.customer_service import get_customer_reply_provider

    app.dependency_overrides[get_customer_reply_provider] = lambda: provider


def _service_detail(client, conversation_id, headers):
    response = client.get(f"{SERVICE_CONVERSATIONS_PATH}/{conversation_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _message_count(detail, message_type):
    return sum(message["message_type"] == message_type for message in detail["messages"])


def _new_product(client, product_code="ZN-SB-001"):
    return create_approved_demo_product(
        client,
        _login(client, ROLE_OPERATOR_CONTENT),
        product_code,
    )


def _new_waiting_conversation(client):
    conversation = create_customer_conversation(client, _new_product(client)["id"])
    result = ask_customer(client, conversation, "\u4ef7\u683c\u591a\u5c11\uff1f")
    assert result["status"] == "waiting_review"
    return conversation


def test_waiting_review_accepts_supplement_without_side_effects(client):
    provider = CountingProvider()
    _use_provider(provider)
    conversation = _new_waiting_conversation(client)
    service = _login(client, ROLE_CUSTOMER_SERVICE)
    before = _service_detail(client, conversation["id"], service)
    calls_before = provider.total_calls

    result = ask_customer(
        client,
        conversation,
        "\u8865\u5145\uff1a\u5546\u54c1\u662f\u4ec0\u4e48\u6750\u8d28\uff1f",
    )
    after = _service_detail(client, conversation["id"], service)

    assert result["status"] == "waiting_review"
    assert result["reply"] is None
    assert provider.total_calls == calls_before
    assert _message_count(after, "customer") == _message_count(before, "customer") + 1
    assert _message_count(after, "review_draft") == _message_count(before, "review_draft")
    assert _message_count(after, "waiting_notice") == _message_count(before, "waiting_notice")
    assert after["pending_draft"]["id"] == before["pending_draft"]["id"]


def test_transferred_accepts_supplement_without_side_effects(client):
    provider = CountingProvider()
    _use_provider(provider)
    conversation = create_customer_conversation(client, _new_product(client)["id"])
    initial = ask_customer(client, conversation, "\u6211\u8981\u6295\u8bc9\uff0c\u8bf7\u8f6c\u4eba\u5de5")
    assert initial["status"] == "transferred"
    service = _login(client, ROLE_CUSTOMER_SERVICE)
    before = _service_detail(client, conversation["id"], service)
    calls_before = provider.total_calls

    result = ask_customer(
        client,
        conversation,
        "\u8865\u5145\uff1a\u5546\u54c1\u662f\u4ec0\u4e48\u6750\u8d28\uff1f",
    )
    after = _service_detail(client, conversation["id"], service)

    assert result["status"] == "transferred"
    assert result["reply"] is None
    assert provider.total_calls == calls_before == 0
    assert _message_count(after, "customer") == _message_count(before, "customer") + 1
    assert _message_count(after, "transfer_notice") == _message_count(before, "transfer_notice")


def _configure_qwen(monkeypatch, *, api_key="acceptance-fake-key"):
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_provider", "qwen")
    monkeypatch.setattr(settings, "llm_api_base", "https://dashscope.invalid")
    monkeypatch.setattr(settings, "llm_api_key", api_key)
    monkeypatch.setattr(settings, "llm_model", "qwen-plus")


def _qwen_response(content="source-backed answer", *, status_code=200):
    return SimpleNamespace(
        status_code=status_code,
        code=None if status_code == 200 else "provider_failed",
        message=None if status_code == 200 else "mock failure",
        output=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        ),
    )


def test_customer_provider_defaults_to_qwen_when_configured(monkeypatch):
    from app.services.customer_service import get_customer_reply_provider

    _configure_qwen(monkeypatch)
    assert get_customer_reply_provider().name == "qwen"


def test_qwen_customer_provider_success_uses_safe_mocked_parameters(monkeypatch):
    import dashscope
    from app.services.customer_service import get_customer_reply_provider

    _configure_qwen(monkeypatch)
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return _qwen_response()

    monkeypatch.setattr(dashscope.Generation, "call", fake_call)
    answer = get_customer_reply_provider().draft(
        "Could you confirm this item?",
        "material=304 stainless steel; source=product:1:v2",
    )

    assert answer == "source-backed answer"
    assert captured["model"] == "qwen-plus"
    assert captured["result_format"] == "message"
    prompt = json.dumps(captured["messages"], ensure_ascii=False).lower()
    assert "304 stainless steel" in prompt
    for forbidden in ("purchase_cost", "margin", "stock_quantity", "acceptance-fake-key"):
        assert forbidden not in prompt


@pytest.mark.parametrize(
    ("provider_state", "expected_error"),
    (
        ("no_key", "ProviderNoKeyError"),
        ("timeout", "ProviderTimeoutError"),
        ("failed", "ProviderFailedError"),
        ("field_missing", "ProviderFieldMissingError"),
    ),
)
def test_qwen_customer_provider_failure_states_are_reproducible(
    monkeypatch,
    provider_state,
    expected_error,
):
    import dashscope
    import app.services.customer_service as service

    _configure_qwen(
        monkeypatch,
        api_key="" if provider_state == "no_key" else "acceptance-fake-key",
    )
    calls = 0

    def fake_call(**_kwargs):
        nonlocal calls
        calls += 1
        if provider_state == "timeout":
            raise TimeoutError("mock timeout")
        if provider_state == "failed":
            return _qwen_response(status_code=503)
        return _qwen_response(content=None)

    monkeypatch.setattr(dashscope.Generation, "call", fake_call)
    provider = service.get_customer_reply_provider()
    with pytest.raises(getattr(service, expected_error)):
        provider.draft(
            "What is the current price?",
            "material=304 stainless steel; source=product:1:v2",
        )
    assert calls == (0 if provider_state == "no_key" else 1)


def test_customer_message_trim_and_blank_validation(client):
    conversation = create_customer_conversation(client, _new_product(client)["id"])
    content = "\u5546\u54c1\u662f\u4ec0\u4e48\u6750\u8d28\uff1f"
    sent = client.post(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{conversation['id']}/messages",
        headers=customer_headers(conversation["access_token"]),
        json={"content": f"  {content}  "},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["customer_message"]["content"] == content

    blank = client.post(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{conversation['id']}/messages",
        headers=customer_headers(conversation["access_token"]),
        json={"content": " \t\r\n "},
    )
    assert blank.status_code == 422, blank.text
    assert error_detail(blank)["code"] == "validation_error"


def test_service_send_trim_and_blank_validation(client):
    _use_provider(CountingProvider())
    service = _login(client, ROLE_CUSTOMER_SERVICE)
    conversation = _new_waiting_conversation(client)
    sent = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}/send",
        headers=service,
        json={"content": "  reviewed response  "},
    )
    assert sent.status_code == 200, sent.text
    assert any(
        item["message_type"] == "staff_reply" and item["content"] == "reviewed response"
        for item in sent.json()["messages"]
    )

    blank_conversation = _new_waiting_conversation(client)
    blank = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{blank_conversation['id']}/send",
        headers=service,
        json={"content": " \t\r\n "},
    )
    assert blank.status_code == 422, blank.text
    assert error_detail(blank)["code"] == "validation_error"


def test_manual_transfer_trim_and_blank_validation(client):
    service = _login(client, ROLE_CUSTOMER_SERVICE)
    conversation = create_customer_conversation(client, _new_product(client)["id"])
    reason = "customer requested manual review"
    transferred = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{conversation['id']}/transfer",
        headers=service,
        json={"reason": f"  {reason}  "},
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["transfer_reason"] == reason

    blank_conversation = create_customer_conversation(client, _new_product(client)["id"])
    blank = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{blank_conversation['id']}/transfer",
        headers=service,
        json={"reason": " \t\r\n "},
    )
    assert blank.status_code == 422, blank.text
    assert error_detail(blank)["code"] == "validation_error"


def test_business_body_is_preserved_but_audit_and_logs_are_redacted(client, caplog):
    _use_provider(CountingProvider())
    phone = "13800138000"
    address = "Gate3 Road 88"
    fake_token = "tok_test_gate3_9f8e7d6c"
    sentinels = (phone, address, fake_token)
    service = _login(client, ROLE_CUSTOMER_SERVICE)

    waiting = create_customer_conversation(client, _new_product(client)["id"])
    question = f"\u4ef7\u683c\u591a\u5c11\uff1f phone={phone}; address={address}; token={fake_token}"
    assert ask_customer(client, waiting, question)["status"] == "waiting_review"
    edited = f"manual reply phone={phone}; address={address}; token={fake_token}"
    sent = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{waiting['id']}/send",
        headers=service,
        json={"content": edited},
    )
    assert sent.status_code == 200, sent.text
    assert any(item["content"] == edited for item in sent.json()["messages"])

    transferred = create_customer_conversation(client, _new_product(client)["id"])
    reason = f"phone={phone}; address={address}; token={fake_token}"
    transfer = client.post(
        f"{SERVICE_CONVERSATIONS_PATH}/{transferred['id']}/transfer",
        headers=service,
        json={"reason": reason},
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["transfer_reason"] == reason

    response = client.get(AUDIT_EVENTS_PATH, headers=_login(client, ROLE_ADMIN))
    assert response.status_code == 200, response.text
    events = [
        item
        for item in response.json()["items"]
        if item["target_id"] in {waiting["id"], transferred["id"]}
    ]
    draft = next(
        item
        for item in events
        if item["target_id"] == waiting["id"] and item["action"] == "draft.edited"
    )
    draft_before = json.loads(draft["before_json"] or "{}")
    draft_after = json.loads(draft["after_json"] or "{}")
    for forbidden_key in ("content", "original_draft", "final_content"):
        assert forbidden_key not in draft_before
        assert forbidden_key not in draft_after
    transfer_audit = next(
        item
        for item in events
        if item["target_id"] == transferred["id"]
        and item["action"] == "conversation.transferred"
    )
    draft_text = json.dumps(draft, ensure_ascii=False)
    transfer_text = json.dumps(transfer_audit, ensure_ascii=False)
    assert "manual_transfer" in transfer_text
    evidence = draft_text + transfer_text + response.text + caplog.text
    for sentinel in sentinels:
        assert sentinel not in evidence
