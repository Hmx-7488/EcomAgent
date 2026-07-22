"""Image generation API routes."""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.asset import (
    AssetListResponse,
    AssetRead,
    ImageGenerateRequest,
    ImageTaskCreateResponse,
    ImageTaskRead,
)
from ..services import image_service

router = APIRouter(prefix="/api/images", tags=["images"])


@router.post("/upload", response_model=AssetRead, status_code=201)
def api_upload_image(
    product_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a product source image for generation."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    content = file.file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="Image too large (max 10 MB)")

    asset = image_service.save_upload(db, product_id, content, file.filename)
    return asset


@router.post("/generate", response_model=ImageTaskCreateResponse, status_code=202)
def api_create_image_task(
    data: ImageGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Create an image generation task. Runs asynchronously."""
    # Get the latest source asset for this product
    source_assets = image_service.get_product_assets(
        db, data.product_id, asset_type="source"
    )
    if not source_assets:
        raise HTTPException(
            status_code=400,
            detail="No source image uploaded for this product. Upload an image first.",
        )
    source_id = source_assets[0].id

    task = image_service.create_generation_task(
        db, data.product_id, source_id, data.style
    )

    # Queue async processing
    background_tasks.add_task(image_service.process_generation_task, db, task.id)

    return ImageTaskCreateResponse(task_id=task.id, status=task.status)


@router.get("/tasks/{task_id}", response_model=ImageTaskRead)
def api_get_task_status(task_id: int, db: Session = Depends(get_db)):
    """Poll image generation task status."""
    task = image_service.get_task_status(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/assets/{product_id}", response_model=AssetListResponse)
def api_get_product_assets(
    product_id: int,
    asset_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all assets for a product."""
    assets = image_service.get_product_assets(
        db, product_id, asset_type=asset_type
    )
    return AssetListResponse(
        items=[AssetRead.model_validate(a) for a in assets],
        total=len(assets),
    )