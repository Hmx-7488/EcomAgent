"""Schemas for P0 content packages, approvals, exports and audit evidence."""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

CONTENT_FIELDS = {"title", "selling_points", "detail", "parameters", "faq", "sales_script", "promo_material"}

class ContentPackageCreate(BaseModel):
    product_id: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)

class ContentPackageUpdate(BaseModel):
    payload: dict[str, Any]

class ContentGenerateRequest(BaseModel):
    product_id: Optional[int] = Field(default=None, ge=1) # legacy route compatibility
    package_id: Optional[int] = Field(default=None, ge=1)
    platform: str = Field(default="general", max_length=64)
    content_type: str = Field(default="title", max_length=64)
    style_hint: Optional[str] = Field(None, max_length=512)

class ContentTransitionRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)

class ContentVersionRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    id: int; version_no: int; payload: dict[str, Any]; provider: str
    model_name: Optional[str]; task_status: str; error_summary: Optional[str]; created_at: datetime

class ContentPackageRead(BaseModel):
    id: int; product_id: int; source_fact_version: str; source_summary: str
    status: str; current_version_no: int; created_by_id: int; created_at: datetime; updated_at: datetime
    versions: list[ContentVersionRead] = Field(default_factory=list)

class ContentPackageListResponse(BaseModel):
    items: list[ContentPackageRead]; total: int

class MarkdownExportRead(BaseModel):
    package_id: int; markdown: str; exported_at: datetime

class AuditEventRead(BaseModel):
    id: int; action: str; target_type: str; target_id: int; actor_id: Optional[int]
    before_json: Optional[str]; after_json: Optional[str]
    summary: Optional[str]; created_at: datetime
    model_config = {"from_attributes": True}

class AuditEventListResponse(BaseModel):
    items: list[AuditEventRead]; total: int

# Kept for old direct-service tests and legacy read endpoints.
class ContentGenerateResponse(BaseModel):
    id: int; product_id: int; content_type: str; platform: str; content_json: Optional[str]; created_at: datetime
    model_config = {"from_attributes": True}
class ContentVersionListResponse(BaseModel):
    items: list[ContentGenerateResponse]; total: int
class ToolCallLogRead(BaseModel):
    id: int; conversation_id: Optional[int]; tool_name: str; arguments_json: Optional[str]; result_summary: Optional[str]; status: str; latency_ms: Optional[int]; error_message: Optional[str]; created_at: datetime
    model_config = {"from_attributes": True}
class ToolCallLogListResponse(BaseModel):
    items: list[ToolCallLogRead]; total: int
