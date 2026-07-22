"""Pydantic schemas for assets and image generation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Asset ---

class AssetRead(BaseModel):
    id: int
    product_id: int
    asset_type: str
    source_type: Optional[str]
    url: str
    width: Optional[int]
    height: Optional[int]
    metadata_json: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    items: list[AssetRead]
    total: int


# --- Image Generation ---

STYLE_CHOICES = [
    "home", "outdoor", "summer", "minimal", "live", "promotion"
]


class ImageGenerateRequest(BaseModel):
    product_id: int = Field(ge=1)
    style: str = Field(
        description="Scene style: home, outdoor, summer, minimal, live, promotion"
    )


class ImageTaskRead(BaseModel):
    id: int
    product_id: int
    source_asset_id: Optional[int]
    status: str
    style: str
    model_name: Optional[str]
    prompt: Optional[str]
    result_asset_ids: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImageTaskCreateResponse(BaseModel):
    task_id: int
    status: str
    message: str = "Image generation task created. Poll /api/images/tasks/{task_id} for results."
