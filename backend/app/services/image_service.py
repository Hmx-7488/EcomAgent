"""Image upload and generation service (Qwen Image / DashScope)."""

import base64
import json
import mimetypes
import os
import time
import uuid
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.asset import Asset, ImageGenerationTask
from ..models.product import Product
from ..models.content import ApprovalRecord
from ..models.user import User
from .content_service import _audit

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _validate_upload(filename: str, file_bytes: bytes) -> None:
    """Validate uploaded file before saving."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large: {len(file_bytes)} bytes. Maximum: {MAX_FILE_SIZE} bytes"
        )


class ProviderNoKeyError(RuntimeError): pass
class ProviderTimeoutError(RuntimeError): pass
class ProviderFailedError(RuntimeError): pass
class ProviderFieldMissingError(RuntimeError): pass

def save_upload(db: Session, product_id: int, file_bytes: bytes, filename: str, asset_type: str = "reference") -> Asset:
    """Save an uploaded image and create an Asset record."""
    _validate_upload(filename, file_bytes)
    ext = os.path.splitext(filename)[1].lower() or ".png"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, unique_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)

    asset = Asset(
        product_id=product_id,
        asset_type=asset_type,
        source_type="upload",
        url=f"/uploads/{unique_name}",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_generation_task(
    db: Session, product_id: int, source_asset_id: Optional[int], style: str
) -> ImageGenerationTask:
    """Create an image generation task and queue it for processing."""
    product = db.query(Product).filter(Product.id == product_id).first()

    prompt = _build_prompt(product.name if product else "商品", style)

    task = ImageGenerationTask(
        product_id=product_id,
        source_asset_id=source_asset_id,
        style=style,
        model_name=(
            f"google:{settings.google_image_model}"
            if settings.image_provider == "google"
            else "qwen:qwen-image"
        ),
        prompt=prompt,
        provider=settings.image_provider,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def generate_image_with_provider(db: Session, task: ImageGenerationTask) -> list[str]:
    """Injectable boundary: production call only runs when credentials are configured."""
    if not settings.image_gen_configured:
        raise ProviderNoKeyError("Image provider is not configured")
    if settings.image_provider == "google":
        return _call_google_gemini_image(db, task)
    return _call_qwen_image(task)


def process_generation_task(db: Session, task_id: int) -> ImageGenerationTask:
    """Process a pending image generation task.

    If DashScope API is configured, calls Qwen Image.
    Otherwise, creates a placeholder result for MVP demonstration.
    """
    task = db.query(ImageGenerationTask).filter(
        ImageGenerationTask.id == task_id
    ).first()
    if not task:
        raise ValueError(f"Task {task_id} not found")

    task.status = "processing"
    db.commit()

    try:
        result_urls = generate_image_with_provider(db=db, task=task)
        if isinstance(result_urls, dict):
            result_urls = result_urls.get("images")
        if not result_urls:
            raise ProviderFieldMissingError("Provider response did not contain image results")

        # Save generated assets
        asset_ids = []
        for url in result_urls:
            # Provider adapters may return bytes in tests or local workers;
            # persist no binary in audit/DB and expose only a local opaque URL.
            if isinstance(url, bytes):
                output_name = f"{uuid.uuid4().hex}.png"
                with open(os.path.join(UPLOAD_DIR, output_name), "wb") as output_file:
                    output_file.write(url)
                url = f"/uploads/{output_name}"
            asset = Asset(
                product_id=task.product_id,
                asset_type="generated",
                source_type="generation",
                url=url,
                metadata_json=json.dumps(
                    {"style": task.style, "model": task.model_name},
                    ensure_ascii=False,
                ),
            )
            db.add(asset)
            db.flush()
            asset_ids.append(asset.id)

        task.result_asset_ids = json.dumps(asset_ids)
        task.status = "completed"
    except (ProviderTimeoutError, httpx.TimeoutException) as e:
        task.status = "timeout"
        task.error_message = str(e) or "Provider timed out"
    except (ProviderFieldMissingError, ValueError) as e:
        task.status = "field_missing"
        task.error_message = str(e)
    except ProviderNoKeyError as e:
        task.status = "no_key"
        task.error_message = str(e)
    except (ProviderFailedError, Exception) as e:
        task.status = "failed"
        task.error_message = str(e) or "Provider failed"

    db.commit()
    db.refresh(task)
    return task


def get_task_status(db: Session, task_id: int) -> Optional[ImageGenerationTask]:
    return db.query(ImageGenerationTask).filter(
        ImageGenerationTask.id == task_id
    ).first()


def get_product_assets(
    db: Session, product_id: int, asset_type: Optional[str] = None
) -> list[Asset]:
    query = db.query(Asset).filter(Asset.product_id == product_id)
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    return query.order_by(Asset.created_at.desc()).all()


def retry_task(db: Session, actor: User, task: ImageGenerationTask) -> ImageGenerationTask:
    if task.status not in {"no_key", "timeout", "failed", "field_missing"}:
        raise RuntimeError("retry_not_available")
    task.status, task.error_message, task.retry_count = "pending", None, task.retry_count + 1
    _audit(db, actor, "image.retried", "image_task", task.id, after={"status":"pending","retry_count":task.retry_count}, summary="Retried image task")
    db.commit(); db.refresh(task); return task


def confirm_task(db: Session, actor: User, task: ImageGenerationTask) -> ImageGenerationTask:
    if task.status != "completed": raise RuntimeError("completed_image_required")
    task.confirmed_by_id = actor.id; task.confirmed_at = __import__("datetime").datetime.utcnow()
    _audit(db, actor, "image.confirmed", "image_task", task.id, summary="Confirmed image result")
    db.commit(); db.refresh(task); return task


def transition_task(db: Session, actor: User, task: ImageGenerationTask, action: str, reason: Optional[str] = None) -> ImageGenerationTask:
    target = {"submit":"submitted", "approve":"approved", "reject":"rejected"}.get(action)
    if not target or (action == "submit" and (task.approval_status not in {"draft","rejected"} or not task.confirmed_at)) or (action in {"approve","reject"} and task.approval_status != "submitted"):
        raise RuntimeError("illegal_status_transition")
    if action == "reject" and not reason: raise ValueError("rejection_reason_required")
    task.approval_status = target
    if action == "reject": task.rejection_reason = reason
    db.add(ApprovalRecord(target_type="image_task", target_id=task.id, status=target, reason=reason, actor_id=actor.id))
    _audit(db, actor, f"image.{target}", "image_task", task.id, after={"approval_status":target}, summary=reason or f"Image {action}")
    db.commit(); db.refresh(task); return task


def export_task(db: Session, actor: User, task: ImageGenerationTask) -> dict:
    if task.status != "completed" or not task.confirmed_at or task.approval_status != "approved":
        raise RuntimeError("approval_required")
    ids = json.loads(task.result_asset_ids or "[]")
    _audit(db, actor, "image.exported", "image_task", task.id, summary="Exported approved confirmed image")
    db.commit()
    return {"task_id":task.id, "asset_ids":ids, "exported_at":__import__("datetime").datetime.utcnow()}


def _build_prompt(product_name: str, style: str) -> str:
    """Build a Qwen Image prompt based on product and style."""
    style_descriptions = {
        "home": "温馨居家环境，自然光线，柔和色调",
        "outdoor": "户外自然环境，阳光明媚，清新氛围",
        "summer": "夏日清爽氛围，明亮色彩，海滩或泳池背景",
        "minimal": "极简白色背景，专业产品摄影风格，柔和阴影",
        "live": "直播间氛围，环形灯打光，带货展示台",
        "promotion": "节日促销氛围，红色金色点缀，打折标签感",
    }
    style_desc = style_descriptions.get(style, style_descriptions["minimal"])
    return (
        f"电商产品图：{product_name}，{style_desc}。"
        f"产品居中摆放，高清商业摄影，专业打光，电商平台主图风格。"
    )


def _call_qwen_image(task: ImageGenerationTask) -> list[str]:
    """Call DashScope Qwen Image API for background replacement."""
    import httpx

    response = httpx.post(
        f"{settings.image_gen_api_base}/services/aigc/image-generation/generation",
        headers={"Authorization": f"Bearer {settings.image_gen_api_key}"},
        json={
            "model": "qwen-image",
            "input": {
                "prompt": task.prompt,
            },
            "parameters": {
                "size": "1024*1024",
                "n": 3,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return [
        img["url"] for img in data.get("output", {}).get("results", [])
    ]


def _call_google_gemini_image(db: Session, task: ImageGenerationTask) -> list[str]:
    """Edit a source product image with Gemini and store the returned asset locally."""
    source_asset = None
    if task.source_asset_id:
        source_asset = db.query(Asset).filter(Asset.id == task.source_asset_id).first()
    if not source_asset or not source_asset.url.startswith("/uploads/"):
        raise RuntimeError("Google image generation requires an uploaded source product image")

    filename = source_asset.url.rsplit("/", 1)[-1]
    source_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(source_path):
        raise RuntimeError("Source product image is no longer available")

    with open(source_path, "rb") as source_file:
        source_bytes = source_file.read()
    mime_type = mimetypes.guess_type(source_path)[0] or "image/png"
    payload = {
        "model": settings.google_image_model,
        "input": [
            {"type": "image", "mime_type": mime_type, "data": base64.b64encode(source_bytes).decode("ascii")},
            {"type": "text", "text": task.prompt or "Generate a clean e-commerce product scene."},
        ],
        "response_format": {"type": "image", "aspect_ratio": "1:1", "image_size": "1K"},
    }
    response = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"x-goog-api-key": settings.google_api_key},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    image_data = _extract_google_image_data(response.json())

    output_name = f"{uuid.uuid4().hex}.png"
    with open(os.path.join(UPLOAD_DIR, output_name), "wb") as output_file:
        output_file.write(base64.b64decode(image_data))
    return [f"/uploads/{output_name}"]


def _extract_google_image_data(response: dict) -> str:
    """Extract the final image payload from Gemini's Interactions API response."""
    output_image = response.get("output_image")
    if isinstance(output_image, dict) and output_image.get("data"):
        return output_image["data"]
    for step in reversed(response.get("steps", [])):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if block.get("type") == "image" and block.get("data"):
                return block["data"]
    raise RuntimeError("Gemini response did not contain an image output")


def _placeholder_result(task: ImageGenerationTask) -> list[str]:
    """Return placeholder when image API is not configured (MVP demo)."""
    time.sleep(2)  # Simulate processing delay
    return [
        f"/uploads/placeholder_{task.style}_1.png",
        f"/uploads/placeholder_{task.style}_2.png",
        f"/uploads/placeholder_{task.style}_3.png",
    ]
