"""Source-traceable P0 presales routing.

Low-risk facts use deterministic templates. Medium-risk internal drafts use the
configured DashScope/Qwen provider, while tests must never call the real network.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

import httpx
from sqlalchemy.orm import Session
from ..core.config import settings
from ..models.content import (AuditEvent, ContentPackage, ContentVersion, Conversation,
    ConversationDecision, ConversationFactSource, ConversationMessage)
from ..models.product import Product, SKU
from ..models.user import User

TRANSFER_MESSAGE = "\u5df2\u8f6c\u4eba\u5de5\uff0c\u8bf7\u7b49\u5f85\u5ba2\u670d\u5904\u7406"
WAITING_MESSAGE = "\u95ee\u9898\u5df2\u63d0\u4ea4\u5ba2\u670d\u5ba1\u6838\uff0c\u8bf7\u7a0d\u5019\u67e5\u770b\u56de\u590d"

class ProviderNoKeyError(RuntimeError): pass
class ProviderTimeoutError(RuntimeError): pass
class ProviderFailedError(RuntimeError): pass
class ProviderFieldMissingError(RuntimeError): pass

class CustomerReplyProvider(Protocol):
    name: str
    def reply(self, fact_text: str) -> str: ...
    def draft(self, question: str, safe_fact_summary: str = "") -> str: ...

class LocalTemplateProvider:
    name = "local_template"
    def reply(self, fact_text: str) -> str: return fact_text
    def draft(self, question: str, safe_fact_summary: str = "") -> str:
        del question, safe_fact_summary
        return "\u8be5\u95ee\u9898\u9700\u8981\u5ba2\u670d\u6839\u636e\u5df2\u5ba1\u6838\u8d44\u6599\u8fdb\u4e00\u6b65\u786e\u8ba4\u540e\u56de\u590d\u3002"


class QwenCustomerReplyProvider:
    """DashScope adapter whose model payload contains only safe presales text."""

    name = "qwen"

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model or "qwen-plus"

    def reply(self, fact_text: str) -> str:
        # Low-risk facts are answered deterministically by the domain service.
        return fact_text

    def draft(self, question: str, safe_fact_summary: str = "") -> str:
        if not self._api_key:
            raise ProviderNoKeyError("Qwen is not configured")
        try:
            import dashscope

            response = dashscope.Generation.call(
                model=self._model,
                api_key=self._api_key,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是售前客服内部草稿助手。只能依据提供的安全事实摘要起草，"
                            "不得承诺价格、库存、物流时效或售后裁决；信息不足时明确建议人工确认。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"顾客问题：{question}\n安全事实摘要：{safe_fact_summary or '无'}",
                    },
                ],
                result_format="message",
                max_tokens=512,
                request_timeout=30,
            )
        except ProviderNoKeyError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderTimeoutError("Qwen timed out") from exc
        except Exception as exc:
            if "timeout" in exc.__class__.__name__.lower():
                raise ProviderTimeoutError("Qwen timed out") from exc
            raise ProviderFailedError("Qwen request failed") from exc
        if getattr(response, "status_code", None) != 200:
            raise ProviderFailedError("Qwen returned a non-success status")
        try:
            content = response.output.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise ProviderFieldMissingError("Qwen response content is missing") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderFieldMissingError("Qwen response content is missing")
        return content.strip()


def get_customer_reply_provider() -> CustomerReplyProvider:
    if settings.llm_provider.lower() == "qwen":
        return QwenCustomerReplyProvider(settings.llm_api_key, settings.llm_model)
    return QwenCustomerReplyProvider("", settings.llm_model)

@dataclass
class SafeFact:
    answer: str
    sources: list[dict]


@dataclass
class SupplementalOutcome:
    customer_message_id: int
    risk_level: str
    decision: str
    reason_code: str
    source_summary: str = "[]"

HIGH_RULES = (
    ("human_requested", ("\u4eba\u5de5", "\u771f\u4eba", "\u5ba2\u670d\u5904\u7406")),
    ("complaint_or_quality", ("\u6295\u8bc9", "\u8d28\u91cf\u95ee\u9898", "\u574f\u4e86", "\u7834\u635f", "\u6f0f\u6c14")),
    ("after_sales_action", ("\u9a6c\u4e0a\u9000\u6b3e", "\u7ed9\u6211\u9000\u6b3e", "\u6211\u8981\u9000\u8d27", "\u8865\u53d1", "\u6362\u8d27", "\u6539\u5730\u5740", "\u53d6\u6d88\u8ba2\u5355")),
    ("certification_or_claim", ("\u8ba4\u8bc1", "\u98df\u54c1\u7ea7", "\u533b\u7528\u7ea7", "\u73af\u4fdd\u65e0\u6bd2", "\u529f\u6548", "\u6cbb\u7597", "\u9632\u9709", "\u6c38\u4e45", "\u7edd\u5bf9", "\u4fdd\u8bc1", "\u4e00\u5b9a")),
    ("prompt_attack", ("\u5ffd\u7565", "\u7cfb\u7edf\u63d0\u793a", "api_key", "\u5bc6\u94a5", "\u7ed5\u8fc7", "\u81ea\u7531 sql", "\u5176\u4ed6\u5546\u5bb6", "\u8bad\u7ec3")),
    ("unsupported_action", ("\u53d1\u5e03", "\u6295\u653e", "\u8c03\u4ef7", "\u521b\u5efa\u8865\u53d1\u5355")),
)
MEDIUM_RULES = (
    ("price_or_inventory", ("\u4ef7\u683c", "\u591a\u5c11\u94b1", "\u8d35\u591a\u5c11", "\u5e93\u5b58", "\u73b0\u8d27")),
    ("promotion", ("\u4f18\u60e0", "\u6d3b\u52a8", "\u6298\u6263", "\u7279\u4ef7", "\u4f18\u60e0\u5238", "\u6700\u4f4e\u4ef7")),
    ("shipping_commitment", ("\u53d1\u8d27", "\u5230\u8d27", "\u7269\u6d41", "\u9001\u5230", "\u6536\u5230\u8d27", "\u660e\u5929\u80fd\u5230", "\u4ec0\u4e48\u65f6\u5019")),
    ("policy_judgement", ("\u552e\u540e", "\u8fd0\u8d39", "\u4e03\u5929", "7\u5929", "\u65e0\u7406\u7531", "\u9000\u6b3e", "\u9000\u8d27")),
)
LOW_FIELDS = (
    ("material", ("\u6750\u8d28", "\u6750\u6599")), ("size", ("\u5c3a\u5bf8", "\u591a\u5927", "\u89c4\u683c")),
    ("package", ("\u5305\u88c5", "\u6e05\u5355", "\u51e0\u4e2a\u76d2", "\u51e0\u4e2a\u88c5")),
    ("capacity", ("\u5bb9\u91cf", "\u591a\u5c11\u5347", "\u51e0\u4e2a\u888b", "\u5305\u542b")),
    ("color", ("\u989c\u8272", "\u4ec0\u4e48\u8272")),
    ("usage", ("\u5b89\u88c5", "\u600e\u4e48\u7528", "\u4f7f\u7528", "\u80fd\u62c6", "\u62bd\u6c14\u6cf5", "\u91cd\u590d\u7528")),
    ("scene", ("\u9002\u5408", "\u573a\u666f", "\u653e\u5728\u54ea\u91cc", "\u6536\u7eb3\u4ec0\u4e48", "\u80fd\u653e", "\u516c\u65a4")),
)

def _audit(db: Session, action: str, conversation_id: int, *, summary: str,
           actor_id: Optional[int] = None, before: Optional[dict] = None,
           after: Optional[dict] = None) -> None:
    db.add(AuditEvent(action=action, target_type="conversation", target_id=conversation_id,
        actor_id=actor_id, before_json=json.dumps(before, ensure_ascii=False) if before else None,
        after_json=json.dumps(after, ensure_ascii=False) if after else None, summary=summary))

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def create_customer_conversation(db: Session, product_id: int) -> tuple[Conversation, str]:
    product = db.get(Product, product_id)
    if not product or product.is_deleted or product.status != "approved":
        raise LookupError("approved_product_not_found")
    token = secrets.token_urlsafe(32)
    item = Conversation(product_id=product.id, token_digest=_digest(token),
        title=f"\u5546\u54c1\u54a8\u8be2 #{product.id}", status="open")
    db.add(item); db.flush()
    _audit(db, "conversation.created", item.id, summary="Anonymous presales conversation created",
        after={"status": "open", "product_id": product.id})
    db.commit(); db.refresh(item)
    return item, token

def authorize_customer_conversation(db: Session, conversation_id: int, token: str) -> Conversation:
    digest = _digest(token)
    item = db.query(Conversation).filter(Conversation.id == conversation_id,
        Conversation.token_digest == digest).first()
    if not item or not hmac.compare_digest(item.token_digest or "", digest):
        raise PermissionError("conversation_access_denied")
    return item

def _parameters(product: Product) -> dict:
    try:
        data = json.loads(product.parameters_json or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}

def _source(product: Product, field: str, value: str, *, sku: Optional[SKU] = None) -> dict:
    stamp = product.updated_at or product.created_at
    return {"source_type": "sku" if sku else "product", "source_object_id": sku.id if sku else product.id,
        "source_version": stamp.isoformat(), "field_summary": f"{field}={value}", "data_time": stamp}

def _pick_sku(question: str, skus: list[SKU]) -> Optional[SKU]:
    def matches(sku: SKU) -> bool:
        name_tokens = [part for part in sku.sku_name.split() if len(part) >= 2]
        return sku.sku_name in question or any(part in question for part in name_tokens) or any(
            value and value in question for value in (sku.color, sku.size, sku.spec))
    found = [sku for sku in skus if matches(sku)]
    return found[0] if len(found) == 1 else skus[0] if len(skus) == 1 else None


def _safe_provider_fact_summary(db: Session, product: Product) -> str:
    """Build a strict allowlist summary before crossing the Provider boundary."""
    params = _parameters(product)
    allowed_keys = {
        "material", "\u6750\u8d28", "size", "\u5c3a\u5bf8", "capacity", "\u5bb9\u91cf",
        "color", "\u989c\u8272", "package", "packaging", "\u5305\u88c5",
        "usage", "installation", "\u4f7f\u7528\u65b9\u5f0f",
        "applicable_scene", "scene", "\u9002\u7528\u573a\u666f", "load_note",
    }
    safe_parameters = {
        key: str(value).strip()
        for key, value in params.items()
        if key in allowed_keys and value is not None and str(value).strip()
    }
    skus = db.query(SKU).filter(
        SKU.product_id == product.id,
        SKU.is_deleted == False,
        SKU.status == "active",
    ).order_by(SKU.id).all()  # noqa: E712
    safe_skus = [
        {
            "sku_id": sku.id,
            "name": sku.sku_name,
            "color": sku.color,
            "size": sku.size,
            "spec": sku.spec,
        }
        for sku in skus
    ]
    payload = {
        "product_id": product.id,
        "product_name": product.name,
        "parameters": safe_parameters,
        "sku_specs": safe_skus,
        "approved_rule": (product.shipping_rule_text or "").strip(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _faq_fact(db: Session, product: Product, question: str) -> Optional[SafeFact]:
    current_fact_version = (product.updated_at or product.created_at).isoformat()
    packages = db.query(ContentPackage).filter(ContentPackage.product_id == product.id,
        ContentPackage.status == "approved",
        ContentPackage.source_fact_version == current_fact_version).all()
    for package in packages:
        version = db.query(ContentVersion).filter(ContentVersion.package_id == package.id).order_by(
            ContentVersion.version_no.desc()).first()
        if not version: continue
        try: payload = json.loads(version.payload_json)
        except (TypeError, json.JSONDecodeError): continue
        faq = payload.get("faq", []) if isinstance(payload, dict) else []
        if isinstance(faq, dict): faq = [faq]
        for row in faq if isinstance(faq, list) else []:
            if not isinstance(row, dict): continue
            q = str(row.get("q") or row.get("question") or "")
            answer = str(row.get("a") or row.get("answer") or "")
            if q and answer and (q in question or question in q):
                return SafeFact(answer, [{"source_type": "content_version", "source_object_id": version.id,
                    "source_version": str(version.version_no), "field_summary": "approved_faq", "data_time": version.created_at}])
    return None

def _low_fact(db: Session, product: Product, question: str, field: str) -> Optional[SafeFact]:
    params = _parameters(product)
    skus = db.query(SKU).filter(SKU.product_id == product.id, SKU.is_deleted == False,
        SKU.status == "active").all()  # noqa: E712
    sku = _pick_sku(question, skus)
    if field == "material":
        structured = str(params.get("material") or "")
        description = product.description or ""
        known = {"PP", "PVC", "PE", "PA", "\u65e0\u7eba\u5e03"}
        structured_tokens = {token for token in known if token.lower() in structured.lower()}
        description_tokens = {token for token in known if token.lower() in description.lower()}
        if structured_tokens and description_tokens - structured_tokens:
            raise ValueError("fact_conflict")
    aliases = {"material": ("material", "\u6750\u8d28"), "capacity": ("capacity", "\u5bb9\u91cf"),
        "package": ("package", "packaging", "\u5305\u88c5"), "usage": ("usage", "installation", "\u4f7f\u7528\u65b9\u5f0f"),
        "scene": ("applicable_scene", "scene", "\u9002\u7528\u573a\u666f"), "color": ("color", "\u989c\u8272"),
        "size": ("size", "\u5c3a\u5bf8")}
    if field in {"size", "color", "capacity"} and sku:
        if field == "size":
            value = sku.size
        elif field == "color":
            value = sku.color
        elif "\u51e0\u4e2a\u888b" in question or "\u5305\u542b" in question:
            value = sku.size or sku.spec
        else:
            value = next((part for part in sku.sku_name.split() if "L" in part.upper()), None)
        if value: return SafeFact(f"{sku.sku_name}\uff1a{value}", [_source(product, field, value, sku=sku)])
    if field == "usage" and "\u91cd\u590d\u7528" in question and "\u91cd\u590d" in (product.selling_points or ""):
        text = product.selling_points.strip()
        return SafeFact(text, [_source(product, "selling_points", text)])
    if field == "scene" and ("\u516c\u65a4" in question or "\u627f\u91cd" in question):
        value = params.get("load_note")
        if value: return SafeFact(str(value), [_source(product, "load_note", str(value))])
    for key in aliases[field]:
        value = params.get(key)
        if value is not None and str(value).strip():
            text = str(value).strip()
            return SafeFact(text, [_source(product, key, text)])
    if field == "scene":
        text = product.description or product.selling_points or ""
        if text.strip(): return SafeFact(text.strip(), [_source(product, "description", text.strip())])
    if field == "usage":
        text = product.selling_points or product.description or ""
        if text.strip(): return SafeFact(text.strip(), [_source(product, "description", text.strip())])
    return _faq_fact(db, product, question)

def _match(question: str, rules) -> Optional[str]:
    lowered = question.lower()
    return next((code for code, words in rules if any(word.lower() in lowered for word in words)), None)

def _save_decision(db: Session, conversation: Conversation, message: ConversationMessage, *,
        risk: str, decision: str, reason: str, provider_status: Optional[str],
        sources: list[dict], fact_status: Optional[str] = None):
    public = [{key: value.isoformat() if isinstance(value, datetime) else value for key, value in src.items()}
        for src in sources]
    record = ConversationDecision(conversation_id=conversation.id, customer_message_id=message.id,
        risk_level=risk, decision=decision, reason_code=reason,
        source_summary=json.dumps(public, ensure_ascii=False), provider_status=provider_status)
    db.add(record); db.flush()
    for src in sources:
        db.add(ConversationFactSource(decision_id=record.id, source_type=src["source_type"],
            source_object_id=src["source_object_id"], source_version=src["source_version"],
            field_summary=src["field_summary"], data_time=src["data_time"]))
    _audit(db, "risk.assessed", conversation.id, summary=f"{risk}:{decision}:{reason}",
        after={"risk_level": risk, "decision": decision, "reason_code": reason})
    if fact_status is not None:
        _audit(db, "fact.queried", conversation.id,
            summary=f"Fact lookup {fact_status}; {len(sources)} approved source(s) recorded",
            after={"decision_id": record.id, "source_count": len(sources), "fact_status": fact_status})
    return record

def _transfer(db: Session, conversation: Conversation, message: ConversationMessage, reason: str,
        provider_status: Optional[str] = None, *, sources: Optional[list[dict]] = None,
        fact_status: Optional[str] = None):
    before = conversation.status
    conversation.status = "transferred"; conversation.last_risk_level = "high"; conversation.transfer_reason = reason
    decision = _save_decision(db, conversation, message, risk="high", decision="transfer",
        reason=reason, provider_status=provider_status, sources=sources or [], fact_status=fact_status)
    db.add(ConversationMessage(conversation_id=conversation.id, sender_type="system",
        message_type="transfer_notice", content=TRANSFER_MESSAGE, visible_to_customer=True))
    _audit(db, "conversation.transferred", conversation.id, summary=reason)
    _audit(db, "conversation.status_changed", conversation.id, summary="Conversation status changed",
        before={"status": before}, after={"status": "transferred"})
    if provider_status: _audit(db, "provider.degraded", conversation.id,
        summary=f"Provider safely degraded: {provider_status}", after={"provider_status": provider_status})
    return decision

def _provider_failure(db, conversation, message, operation, *, sources=None, fact_status=None):
    try: return operation(), None
    except ProviderNoKeyError: status = "no_key"
    except ProviderTimeoutError: status = "timeout"
    except ProviderFieldMissingError: status = "field_missing"
    except (ProviderFailedError, Exception): status = "failed"
    return None, _transfer(db, conversation, message, f"provider_{status}", status,
        sources=sources, fact_status=fact_status)
def process_customer_message(db: Session, conversation: Conversation, content: str,
        provider: CustomerReplyProvider):
    if conversation.status == "resolved": raise RuntimeError("conversation_resolved")
    normalized = content.strip()
    if not normalized:
        raise ValueError("message_content_required")
    message = ConversationMessage(conversation_id=conversation.id, sender_type="customer",
        message_type="customer", content=normalized, visible_to_customer=True)
    db.add(message); db.flush()
    _audit(db, "message.received", conversation.id, summary="Customer message received",
        after={"message_id": message.id, "status": conversation.status,
            "content_length": len(normalized), "content_sha256": _digest(normalized)})
    if conversation.status in {"waiting_review", "transferred"}:
        outcome = SupplementalOutcome(
            customer_message_id=message.id,
            risk_level="medium" if conversation.status == "waiting_review" else "high",
            decision="review_draft" if conversation.status == "waiting_review" else "transfer",
            reason_code=(
                "supplement_waiting_review"
                if conversation.status == "waiting_review"
                else "supplement_transferred"
            ),
        )
        db.commit()
        return outcome
    product = db.get(Product, conversation.product_id)
    if not product or product.is_deleted or product.status != "approved":
        decision = _transfer(db, conversation, message, "approved_product_required"); db.commit(); return decision
    reason = _match(normalized, HIGH_RULES)
    if reason:
        decision = _transfer(db, conversation, message, reason); db.commit(); return decision
    reason = _match(normalized, MEDIUM_RULES)
    if reason:
        safe_fact_summary = _safe_provider_fact_summary(db, product)
        draft, failure = _provider_failure(
            db,
            conversation,
            message,
            lambda: provider.draft(normalized, safe_fact_summary),
        )
        if failure: decision = failure
        elif not draft: decision = _transfer(db, conversation, message, "provider_field_missing", "field_missing")
        else:
            before = conversation.status; conversation.status = "waiting_review"; conversation.last_risk_level = "medium"
            decision = _save_decision(db, conversation, message, risk="medium", decision="review_draft",
                reason=reason, provider_status=provider.name, sources=[])
            db.add(ConversationMessage(conversation_id=conversation.id, sender_type="system",
                message_type="review_draft", content=draft, visible_to_customer=False))
            db.add(ConversationMessage(conversation_id=conversation.id, sender_type="system",
                message_type="waiting_notice", content=WAITING_MESSAGE, visible_to_customer=True))
            _audit(db, "draft.generated", conversation.id, summary="Internal draft generated")
            _audit(db, "conversation.status_changed", conversation.id, summary="Conversation status changed",
                before={"status": before}, after={"status": "waiting_review"})
        db.commit(); return decision
    field = next((name for name, words in LOW_FIELDS if any(word in normalized for word in words)), None)
    try:
        fact = _low_fact(db, product, normalized, field) if field else None
    except ValueError as exc:
        decision = _transfer(db, conversation, message, str(exc), fact_status="conflict"); db.commit(); return decision
    if not fact:
        decision = _transfer(db, conversation, message, "fact_missing_or_ambiguous",
            fact_status="missing" if field else None); db.commit(); return decision
    reply = fact.answer
    conversation.status = "open"; conversation.last_risk_level = "low"; conversation.transfer_reason = None
    decision = _save_decision(db, conversation, message, risk="low", decision="auto_reply",
        reason=f"whitelist_{field}", provider_status="deterministic_template",
        sources=fact.sources, fact_status="complete")
    db.add(ConversationMessage(conversation_id=conversation.id, sender_type="system",
        message_type="auto_reply", content=reply, visible_to_customer=True))
    _audit(db, "reply.auto_sent", conversation.id, summary="Source-backed low-risk response sent",
        after={"decision_id": decision.id, "source_count": len(fact.sources)})
    db.commit(); return decision

def customer_messages(db: Session, conversation: Conversation):
    return db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conversation.id,
        ConversationMessage.visible_to_customer == True).order_by(ConversationMessage.id).all()  # noqa: E712

def service_send(db: Session, conversation: Conversation, actor: User, content: str):
    if conversation.status != "waiting_review": raise RuntimeError("not_waiting_review")
    normalized = content.strip()
    if not normalized: raise ValueError("message_content_required")
    draft = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conversation.id,
        ConversationMessage.message_type == "review_draft").order_by(ConversationMessage.id.desc()).first()
    if not draft: raise RuntimeError("draft_not_found")
    edited = draft.content != normalized
    staff_message = ConversationMessage(conversation_id=conversation.id, sender_type="customer_service",
        message_type="staff_reply", content=normalized, visible_to_customer=True, actor_id=actor.id)
    db.add(staff_message); db.flush()
    before = conversation.status; conversation.status = "open"
    _audit(db, "draft.edited", conversation.id, actor_id=actor.id,
        summary="Draft reviewed before staff send",
        before={"draft_message_id": draft.id, "content_length": len(draft.content),
            "content_sha256": _digest(draft.content)},
        after={"final_message_id": staff_message.id, "edited": edited,
            "content_length": len(normalized), "content_sha256": _digest(normalized)})
    _audit(db, "reply.agent_sent", conversation.id, actor_id=actor.id, summary="Reviewed reply sent")
    _audit(db, "conversation.status_changed", conversation.id, actor_id=actor.id,
        summary="Conversation status changed", before={"status": before}, after={"status": "open"})
    db.commit(); db.refresh(conversation); return conversation

def service_transfer(db: Session, conversation: Conversation, actor: User, reason: str):
    if conversation.status == "resolved": raise RuntimeError("conversation_resolved")
    normalized = reason.strip()
    if not normalized: raise ValueError("transfer_reason_required")
    before = conversation.status; conversation.status = "transferred"; conversation.last_risk_level = "high"
    conversation.transfer_reason = normalized
    db.add(ConversationMessage(conversation_id=conversation.id, sender_type="system",
        message_type="transfer_notice", content=TRANSFER_MESSAGE, visible_to_customer=True))
    _audit(db, "conversation.transferred", conversation.id, actor_id=actor.id,
        summary="manual_transfer", after={"reason_code": "manual_transfer"})
    _audit(db, "conversation.status_changed", conversation.id, actor_id=actor.id,
        summary="Conversation status changed", before={"status": before}, after={"status": "transferred"})
    db.commit(); db.refresh(conversation); return conversation

def service_resolve(db: Session, conversation: Conversation, actor: User):
    if conversation.status == "resolved": return conversation
    before = conversation.status; conversation.status = "resolved"
    _audit(db, "conversation.status_changed", conversation.id, actor_id=actor.id, summary="Conversation resolved",
        before={"status": before}, after={"status": "resolved"})
    db.commit(); db.refresh(conversation); return conversation
