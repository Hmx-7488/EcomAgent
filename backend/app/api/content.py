"""Content generation and tool call log API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.content import (
    ContentGenerateRequest,
    ContentGenerateResponse,
    ContentVersionListResponse,
    ToolCallLogListResponse,
    ToolCallLogRead,
)
from ..services.content_service import (
    generate_content,
    get_content_history,
    get_tool_call_logs,
)

router = APIRouter(prefix="/api/content", tags=["content"])


@router.post("/generate", response_model=ContentGenerateResponse)
def api_generate_content(data: ContentGenerateRequest, db: Session = Depends(get_db)):
    result = generate_content(
        db,
        product_id=data.product_id,
        platform=data.platform,
        content_type=data.content_type,
        style_hint=data.style_hint,
    )
    if not result:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Product not found")
    return result


@router.get("/history/{product_id}", response_model=ContentVersionListResponse)
def api_get_content_history(
    product_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_content_history(db, product_id, page=page, page_size=page_size)


# --- Tool Call Logs ---

router_logs = APIRouter(prefix="/api/logs", tags=["logs"])


@router_logs.get("", response_model=ToolCallLogListResponse)
def api_get_tool_logs(
    conversation_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_tool_call_logs(
        db, conversation_id=conversation_id, page=page, page_size=page_size
    )
