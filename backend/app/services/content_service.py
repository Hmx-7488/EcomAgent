"""Content generation and tool call log services."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.content import (AuditEvent, ApprovalRecord, ContentPackage, ContentVersion,
                              Conversation, GeneratedContent, ToolCallLog)
from ..models.product import Product, SKU
from ..models.user import User
from .llm_service import PACKAGE_CONTENT_FIELDS, generate_product_content

logger = logging.getLogger(__name__)

class ProviderNoKeyError(RuntimeError): pass
class ProviderTimeoutError(RuntimeError): pass
class ProviderFailedError(RuntimeError): pass
class ProviderFieldMissingError(RuntimeError): pass

PACKAGE_CONTENT_ERROR = "Provider response has incomplete package content"


def _validated_package_payload(payload: object) -> dict[str, str]:
    """Keep only the seven formal fields after a defensive domain check."""
    if not isinstance(payload, dict):
        raise ProviderFieldMissingError(PACKAGE_CONTENT_ERROR)
    normalized = {}
    for field in PACKAGE_CONTENT_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str):
            raise ProviderFieldMissingError(PACKAGE_CONTENT_ERROR)
        value = value.strip()
        if not value:
            raise ProviderFieldMissingError(PACKAGE_CONTENT_ERROR)
        normalized[field] = value
    return normalized

def generate_package_with_provider(product: Product, content_type: str, platform: str, style_hint: Optional[str]) -> dict:
    """Injectable provider boundary. Tests replace this function; it never stores credentials."""
    if not settings.llm_configured:
        raise ProviderNoKeyError("Text provider is not configured")
    result = generate_product_content(product.name, product.category, product.brand or "", product.description or "",
                                      product.selling_points or "", product.parameters_json or "{}", content_type, platform, style_hint)
    if not isinstance(result, dict):
        raise ProviderFieldMissingError("Provider response did not contain structured content")
    return result


# --- Content Generation ---

def generate_content(
    db: Session,
    product_id: int,
    platform: str,
    content_type: str,
    style_hint: Optional[str] = None,
) -> Optional[GeneratedContent]:
    """Generate content with the configured LLM provider or template fallback."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return None

    # Call LLM service — falls back to template if API key not configured
    content = generate_product_content(
        product_name=product.name,
        category=product.category,
        brand=product.brand or "",
        description=product.description or "",
        selling_points=product.selling_points or "",
        parameters_json=product.parameters_json or "{}",
        content_type=content_type,
        platform=platform,
        style_hint=style_hint,
    )

    prompt_version = f"{settings.llm_provider}-v1" if settings.llm_configured else "template-v1"

    record = GeneratedContent(
        product_id=product_id,
        content_type=content_type,
        platform=platform,
        prompt_version=prompt_version,
        content_json=json.dumps(content, ensure_ascii=False),
        created_by="system",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_content_history(
    db: Session, product_id: int, page: int = 1, page_size: int = 20
) -> dict:
    query = db.query(GeneratedContent).filter(
        GeneratedContent.product_id == product_id
    )
    total = query.count()
    items = (
        query.order_by(GeneratedContent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": items, "total": total}


# --- Tool Call Logs ---

def log_tool_call(
    db: Session,
    tool_name: str,
    arguments: dict,
    result_summary: str,
    status: str = "success",
    latency_ms: Optional[int] = None,
    error_message: Optional[str] = None,
    conversation_id: Optional[int] = None,
) -> ToolCallLog:
    log = ToolCallLog(
        conversation_id=conversation_id,
        tool_name=tool_name,
        arguments_json=json.dumps(arguments, ensure_ascii=False),
        result_summary=result_summary,
        status=status,
        latency_ms=latency_ms,
        error_message=error_message,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_tool_call_logs(
    db: Session,
    conversation_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = db.query(ToolCallLog)
    if conversation_id:
        query = query.filter(ToolCallLog.conversation_id == conversation_id)
    total = query.count()
    items = (
        query.order_by(ToolCallLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": items, "total": total}


def create_conversation(db: Session, title: Optional[str] = None) -> Conversation:
    conv = Conversation(title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


# --- P0 M2 controlled content packages ---
def _audit(db: Session, actor: User, action: str, target_type: str, target_id: int,
           before: Optional[dict] = None, after: Optional[dict] = None, summary: str = "") -> None:
    """Record safe business evidence; callers must never pass credentials."""
    db.add(AuditEvent(action=action, target_type=target_type, target_id=target_id,
                      actor_id=actor.id, before_json=json.dumps(before, ensure_ascii=False) if before else None,
                      after_json=json.dumps(after, ensure_ascii=False) if after else None, summary=summary))


def _approved_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product or product.is_deleted:
        raise LookupError("product_not_found")
    if product.status != "approved":
        raise ValueError("approved_product_required")
    return product


def _fact_summary(db: Session, product: Product) -> tuple[str, str]:
    """Content source deliberately excludes prices, inventory and all cost facts."""
    skus = db.query(SKU).filter(SKU.product_id == product.id, SKU.is_deleted == False).all()  # noqa: E712
    facts = {"product": {"name": product.name, "category": product.category, "brand": product.brand,
                         "description": product.description, "selling_points": product.selling_points,
                         "parameters": product.parameters_json, "shipping_rule": product.shipping_rule_text},
             "skus": [{"name": sku.sku_name, "color": sku.color, "size": sku.size, "spec": sku.spec} for sku in skus]}
    version = product.updated_at.isoformat() if product.updated_at else product.created_at.isoformat()
    return version, json.dumps(facts, ensure_ascii=False, sort_keys=True)


def _version_read(version: ContentVersion) -> dict:
    return {"id": version.id, "version_no": version.version_no, "payload": json.loads(version.payload_json),
            "provider": version.provider, "model_name": version.model_name, "task_status": version.task_status,
            "error_summary": version.error_summary, "created_at": version.created_at}


def package_read(db: Session, package: ContentPackage) -> dict:
    versions = db.query(ContentVersion).filter(ContentVersion.package_id == package.id).order_by(ContentVersion.version_no).all()
    return {"id": package.id, "product_id": package.product_id, "source_fact_version": package.source_fact_version,
            "source_summary": package.source_summary, "status": package.status,
            "current_version_no": package.current_version_no, "created_by_id": package.created_by_id,
            "created_at": package.created_at, "updated_at": package.updated_at,
            "versions": [_version_read(v) for v in versions]}


def create_package(db: Session, actor: User, product_id: int, payload: dict) -> ContentPackage:
    product = _approved_product(db, product_id)
    version, summary = _fact_summary(db, product)
    package = ContentPackage(product_id=product_id, source_fact_version=version, source_summary=summary, created_by_id=actor.id)
    db.add(package); db.flush()
    db.add(ContentVersion(package_id=package.id, version_no=1, payload_json=json.dumps(payload, ensure_ascii=False),
                          provider="manual", task_status="completed", created_by_id=actor.id))
    _audit(db, actor, "content.created", "content_package", package.id, after={"status":"draft"}, summary="Created content package")
    db.commit(); db.refresh(package); return package


def edit_package(db: Session, actor: User, package: ContentPackage, payload: dict) -> ContentPackage:
    if package.status == "approved":
        raise RuntimeError("approved_version_immutable")
    before = {"status": package.status, "version": package.current_version_no}
    if package.status == "rejected": package.status = "draft"
    package.current_version_no += 1
    db.add(ContentVersion(package_id=package.id, version_no=package.current_version_no,
                          payload_json=json.dumps(payload, ensure_ascii=False), provider="manual", task_status="completed", created_by_id=actor.id))
    _audit(db, actor, "content.edited", "content_package", package.id, before=before,
           after={"status":package.status,"version":package.current_version_no}, summary="Saved a new content version")
    db.commit(); db.refresh(package); return package


def generate_package(db: Session, actor: User, package: ContentPackage, content_type: str, platform: str, style_hint: Optional[str]) -> ContentPackage:
    if package.status == "approved": raise RuntimeError("approved_version_immutable")
    product = _approved_product(db, package.product_id)
    package.current_version_no += 1
    provider = settings.llm_provider
    model = settings.google_text_model if provider == "google" else settings.llm_model
    status, payload, error = "completed", {}, None
    try:
        payload = generate_package_with_provider(product=product, content_type=content_type, platform=platform, style_hint=style_hint)
        if content_type == "package":
            payload = _validated_package_payload(payload)
        elif not payload or any(value is None for value in payload.values()):
            raise ProviderFieldMissingError("Provider response has required fields missing")
    except ProviderNoKeyError as exc:
        status, error, provider = "no_key", str(exc), "none"
    except (ProviderTimeoutError, __import__("httpx").TimeoutException) as exc:
        status, error = "timeout", str(exc) or "Provider timed out"
    except (ProviderFieldMissingError, ValueError) as exc:
        status = "field_missing"
        error = PACKAGE_CONTENT_ERROR if content_type == "package" else str(exc)
        payload = {}
    except (ProviderFailedError, Exception):
        status, error = "failed", "Provider failed"
    db.add(ContentVersion(package_id=package.id, version_no=package.current_version_no, payload_json=json.dumps(payload, ensure_ascii=False),
                          provider=provider, model_name=model, task_status=status, error_summary=error, created_by_id=actor.id))
    _audit(db, actor, "content.generated", "content_package", package.id, after={"version":package.current_version_no,"task_status":status}, summary="Generated content version")
    db.commit(); db.refresh(package); return package


def transition_package(db: Session, actor: User, package: ContentPackage, action: str, reason: Optional[str] = None) -> ContentPackage:
    target = {"submit":"submitted", "approve":"approved", "reject":"rejected"}.get(action)
    if not target or (action == "submit" and package.status not in {"draft", "rejected"}) or (action in {"approve", "reject"} and package.status != "submitted"):
        raise RuntimeError("illegal_status_transition")
    if action == "reject" and not reason: raise ValueError("rejection_reason_required")
    before = {"status": package.status}; package.status = target
    db.add(ApprovalRecord(target_type="content_package", target_id=package.id, status=target, reason=reason, actor_id=actor.id))
    _audit(db, actor, f"content.{target}", "content_package", package.id, before=before, after={"status":target}, summary=reason or f"Content package {action}")
    db.commit(); db.refresh(package); return package


def export_package(db: Session, actor: User, package: ContentPackage) -> dict:
    if package.status != "approved": raise RuntimeError("approval_required")
    version = db.query(ContentVersion).filter(ContentVersion.package_id == package.id).order_by(ContentVersion.version_no.desc()).first()
    payload = json.loads(version.payload_json) if version else {}
    markdown = "# Demo 数据：内容素材包\n\n" + "\n\n".join(f"## {key}\n{json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict,list)) else value}" for key, value in payload.items())
    _audit(db, actor, "content.exported", "content_package", package.id, summary="Exported approved Markdown")
    db.commit()
    return {"package_id": package.id, "markdown": markdown, "exported_at": datetime.now(timezone.utc)}
