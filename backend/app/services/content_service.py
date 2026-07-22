"""Content generation and tool call log services."""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.content import Conversation, GeneratedContent, ToolCallLog
from ..models.product import Product
from .llm_service import generate_product_content

logger = logging.getLogger(__name__)


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
