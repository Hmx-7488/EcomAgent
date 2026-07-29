"""Schemas for reference images and controlled P0 image tasks."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class AssetRead(BaseModel):
    id: int; product_id: int; asset_type: str; source_type: Optional[str]; url: str
    width: Optional[int]; height: Optional[int]; metadata_json: Optional[str]
    confirmed_by_id: Optional[int]; confirmed_at: Optional[datetime]; created_at: datetime
    model_config = {"from_attributes": True}
class AssetListResponse(BaseModel): items: list[AssetRead]; total: int
class ImageGenerateRequest(BaseModel):
    product_id: int = Field(ge=1); style: str = Field(default="minimal", max_length=64)
    reference_asset_id: Optional[int] = Field(default=None, ge=1)
class ImageTaskRead(BaseModel):
    id: int; product_id: int; source_asset_id: Optional[int]; status: str; style: str
    model_name: Optional[str]; prompt: Optional[str]; result_asset_ids: Optional[str]; error_message: Optional[str]
    provider: Optional[str]; retry_count: int; approval_status: str; rejection_reason: Optional[str]
    confirmed_by_id: Optional[int]; confirmed_at: Optional[datetime]; created_at: datetime; updated_at: datetime
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
class ImageTaskCreateResponse(BaseModel):
    task_id: int; status: str
class ImageTransitionRequest(BaseModel): reason: Optional[str] = Field(default=None, max_length=2000)
class ImageExportRead(BaseModel): task_id: int; asset_ids: list[int]; exported_at: datetime
