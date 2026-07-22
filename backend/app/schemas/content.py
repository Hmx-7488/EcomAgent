"""Pydantic schemas for content generation and tool call logs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Content Generation ---

class ContentGenerateRequest(BaseModel):
    product_id: int
    platform: str = Field(default="general", max_length=64)
    content_type: str = Field(
        default="title", max_length=64
    )  # title, short_title, selling_points, description, faq, script, keywords
    style_hint: Optional[str] = Field(None, max_length=512)


class ContentGenerateResponse(BaseModel):
    id: int
    product_id: int
    content_type: str
    platform: str
    content_json: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ContentVersionListResponse(BaseModel):
    items: list[ContentGenerateResponse]
    total: int


# --- Tool Call Logs ---

class ToolCallLogRead(BaseModel):
    id: int
    conversation_id: Optional[int]
    tool_name: str
    arguments_json: Optional[str]
    result_summary: Optional[str]
    status: str
    latency_ms: Optional[int]
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ToolCallLogListResponse(BaseModel):
    items: list[ToolCallLogRead]
    total: int
