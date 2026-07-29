"""Image upload and generation service (Qwen Image / DashScope)."""

import base64
import binascii
import json
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.asset import Asset, ImageGenerationTask
from ..models.product import Product
from ..models.content import ApprovalRecord
from ..models.user import User
from .content_service import _audit
from .image_integrity import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    MAX_IMAGE_HEIGHT,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_WIDTH,
    ValidatedImage,
    download_https_image,
    remove_files,
    validate_image_bytes as _validate_image_bytes,
    write_atomic_image,
)

UPLOAD_DIR = os.path.abspath(settings.upload_dir)
os.makedirs(UPLOAD_DIR, exist_ok=True)

def validate_image_bytes(
    file_bytes: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> ValidatedImage:
    """Public unified image-integrity boundary for uploads and Providers."""

    return _validate_image_bytes(
        file_bytes,
        filename=filename,
        content_type=content_type,
        max_file_size=MAX_FILE_SIZE,
        max_image_width=MAX_IMAGE_WIDTH,
        max_image_height=MAX_IMAGE_HEIGHT,
        max_image_pixels=MAX_IMAGE_PIXELS,
    )


def _validate_upload(filename: str, file_bytes: bytes) -> None:
    """Backward-compatible upload validator."""

    validate_image_bytes(file_bytes, filename=filename)

class ProviderNoKeyError(RuntimeError): pass
class ProviderTimeoutError(RuntimeError): pass
class ProviderFailedError(RuntimeError): pass
class ProviderFieldMissingError(RuntimeError): pass

def save_upload(
    db: Session,
    product_id: int,
    file_bytes: bytes,
    filename: str,
    asset_type: str = "reference",
    content_type: str | None = None,
) -> Asset:
    """Validate first, then atomically save and create one Asset transaction."""

    image = validate_image_bytes(
        file_bytes,
        filename=filename,
        content_type=content_type,
    )
    final_path: str | None = None
    try:
        opaque_name, final_path = write_atomic_image(UPLOAD_DIR, file_bytes, image)
        asset = Asset(
            product_id=product_id,
            asset_type=asset_type,
            source_type="upload",
            url=f"/uploads/{opaque_name}",
            width=image.width,
            height=image.height,
            metadata_json=json.dumps(
                {
                    "format": image.format,
                    "size_bytes": image.size_bytes,
                    "transport_content_type": content_type,
                },
                ensure_ascii=False,
            ),
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset
    except Exception:
        db.rollback()
        if final_path:
            remove_files((final_path,))
        raise
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
            settings.google_image_model
            if settings.image_provider == "google"
            else settings.image_gen_model
        ),
        prompt=prompt,
        provider=settings.image_provider,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def generate_image_with_provider(db: Session, task: ImageGenerationTask) -> list[bytes]:
    """Injectable boundary: production call only runs when credentials are configured."""
    if not settings.image_gen_configured:
        raise ProviderNoKeyError("Image provider is not configured")
    if settings.image_provider == "google":
        return _call_google_gemini_image(db, task)
    return _call_qwen_image(db, task)


def _provider_result_bytes(result) -> list[bytes]:
    if isinstance(result, dict):
        result = result.get("images")
    if not isinstance(result, (list, tuple)) or not result:
        raise ProviderFieldMissingError(
            "Provider response did not contain image results"
        )
    payloads: list[bytes] = []
    for item in result:
        if not isinstance(item, (bytes, bytearray)):
            raise ProviderFailedError(
                "Provider result must be downloaded image bytes"
            )
        payloads.append(bytes(item))
    return payloads


def _persist_generated_images(
    db: Session,
    task: ImageGenerationTask,
    payloads: list[bytes],
) -> list[int]:
    """Validate every result before creating files or database rows."""

    validated = [validate_image_bytes(payload) for payload in payloads]
    saved_paths: list[str] = []
    asset_ids: list[int] = []
    try:
        saved: list[tuple[str, str]] = []
        for payload, image in zip(payloads, validated, strict=True):
            persisted = write_atomic_image(UPLOAD_DIR, payload, image)
            saved.append(persisted)
            saved_paths.append(persisted[1])
        for (opaque_name, _path), image in zip(saved, validated, strict=True):
            asset = Asset(
                product_id=task.product_id,
                asset_type="generated",
                source_type="generation",
                url=f"/uploads/{opaque_name}",
                width=image.width,
                height=image.height,
                metadata_json=json.dumps(
                    {
                        "style": task.style,
                        "model": task.model_name,
                        "format": image.format,
                        "size_bytes": image.size_bytes,
                    },
                    ensure_ascii=False,
                ),
            )
            db.add(asset)
            db.flush()
            asset_ids.append(asset.id)
        task.result_asset_ids = json.dumps(asset_ids)
        task.status = "completed"
        task.error_message = None
        db.commit()
        return asset_ids
    except Exception:
        db.rollback()
        remove_files(saved_paths)
        raise


def _mark_task_failure(
    db: Session,
    task_id: int,
    status: str,
    error: Exception,
) -> ImageGenerationTask:
    db.rollback()
    task = db.get(ImageGenerationTask, task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")
    task.status = status
    task.result_asset_ids = None
    task.error_message = (str(error) or "Image task failed")[:512]
    db.commit()
    db.refresh(task)
    return task


def process_generation_task(db: Session, task_id: int) -> ImageGenerationTask:
    """Process one task without permitting unvalidated assets or partial files."""

    task = db.get(ImageGenerationTask, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")
    task.status = "processing"
    task.error_message = None
    db.commit()

    try:
        result = generate_image_with_provider(db=db, task=task)
        payloads = _provider_result_bytes(result)
        _persist_generated_images(db, task, payloads)
    except (ProviderTimeoutError, httpx.TimeoutException) as exc:
        return _mark_task_failure(db, task_id, "timeout", exc)
    except ProviderFieldMissingError as exc:
        return _mark_task_failure(db, task_id, "field_missing", exc)
    except ProviderNoKeyError as exc:
        return _mark_task_failure(db, task_id, "no_key", exc)
    except Exception as exc:
        return _mark_task_failure(db, task_id, "failed", exc)

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
    task.confirmed_by_id = actor.id; task.confirmed_at = datetime.now(timezone.utc)
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
    return {"task_id":task.id, "asset_ids":ids, "exported_at":datetime.now(timezone.utc)}


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


def _reference_image_data_url(
    db: Session,
    task: ImageGenerationTask,
) -> str:
    """Load one validated local reference without exposing its bytes elsewhere."""

    if not task.source_asset_id:
        raise ProviderFieldMissingError("Qwen image editing requires a reference image")
    source_asset = db.get(Asset, task.source_asset_id)
    if not source_asset or not source_asset.url.startswith("/uploads/"):
        raise ProviderFieldMissingError("Qwen reference image is unavailable")

    filename = source_asset.url.rsplit("/", 1)[-1]
    if not filename or filename != os.path.basename(filename):
        raise ProviderFailedError("Qwen reference image path is invalid")
    source_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(source_path):
        raise ProviderFieldMissingError("Qwen reference image is unavailable")
    try:
        with open(source_path, "rb") as source_file:
            source_bytes = source_file.read(MAX_FILE_SIZE + 1)
        source_info = validate_image_bytes(source_bytes, filename=filename)
    except (OSError, ValueError) as exc:
        raise ProviderFailedError("Qwen reference image failed validation") from exc

    mime_type = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
        "BMP": "image/bmp",
    }[source_info.format]
    encoded = base64.b64encode(source_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _qwen_result_urls(data: dict) -> list[str]:
    """Parse the official synchronous multimodal response shape."""

    if not isinstance(data, dict):
        raise ProviderFieldMissingError("Qwen response payload is invalid")
    choices = data.get("output", {}).get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderFieldMissingError("Qwen response omitted output choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ProviderFieldMissingError("Qwen response choice is invalid")
    message = first_choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        raise ProviderFieldMissingError("Qwen response omitted message content")
    urls = [
        item["image"]
        for item in content
        if isinstance(item, dict)
        and isinstance(item.get("image"), str)
        and item["image"]
    ]
    if len(urls) != settings.image_gen_output_count:
        raise ProviderFieldMissingError(
            "Qwen response did not contain all requested images"
        )
    return urls


def _call_qwen_image(db: Session, task: ImageGenerationTask) -> list[bytes]:
    """Call the official Qwen synchronous multimodal image-editing endpoint."""

    reference_data_url = _reference_image_data_url(db, task)
    endpoint = (
        f"{settings.image_gen_api_base.rstrip('/')}"
        "/services/aigc/multimodal-generation/generation"
    )
    request_body = {
        "model": task.model_name or settings.image_gen_model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": reference_data_url},
                        {"text": task.prompt or "基于参考图生成电商场景图。"},
                    ],
                }
            ]
        },
        "parameters": {
            "n": settings.image_gen_output_count,
            "size": "1024*1024",
            "watermark": False,
        },
    }
    try:
        response = httpx.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {settings.image_gen_api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError("Qwen image request timed out") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFailedError("Qwen image request failed") from exc

    urls = _qwen_result_urls(data)
    payloads: list[bytes] = []
    for url in urls:
        try:
            payload = download_https_image(url)
            validate_image_bytes(payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Qwen image download timed out") from exc
        except (RuntimeError, ValueError) as exc:
            raise ProviderFailedError("Qwen image download failed") from exc
        payloads.append(payload)
    return payloads

def _call_google_gemini_image(
    db: Session,
    task: ImageGenerationTask,
) -> list[bytes]:
    """Call Gemini and return verified decoded Base64 bytes, never a URL."""

    source_asset = None
    if task.source_asset_id:
        source_asset = db.get(Asset, task.source_asset_id)
    if not source_asset or not source_asset.url.startswith("/uploads/"):
        raise ProviderFailedError(
            "Google image generation requires a local reference image"
        )

    filename = source_asset.url.rsplit("/", 1)[-1]
    source_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(source_path):
        raise ProviderFailedError("Source product image is no longer available")
    with open(source_path, "rb") as source_file:
        source_bytes = source_file.read()
    source_info = validate_image_bytes(source_bytes, filename=filename)
    mime_type = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
        "BMP": "image/bmp",
    }[source_info.format]

    payload = {
        "model": settings.google_image_model,
        "input": [
            {
                "type": "image",
                "mime_type": mime_type,
                "data": base64.b64encode(source_bytes).decode("ascii"),
            },
            {
                "type": "text",
                "text": task.prompt
                or "Generate a clean e-commerce product scene.",
            },
        ],
        "response_format": {
            "type": "image",
            "aspect_ratio": "1:1",
            "image_size": "1K",
        },
    }
    response = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"x-goog-api-key": settings.google_api_key},
        json=payload,
        timeout=httpx.Timeout(90.0, connect=10.0),
    )
    response.raise_for_status()
    image_data = _extract_google_image_data(response.json())
    try:
        generated_bytes = base64.b64decode(image_data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProviderFailedError(
            "Google image response contained invalid Base64"
        ) from exc
    validate_image_bytes(generated_bytes)
    return [generated_bytes]
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
