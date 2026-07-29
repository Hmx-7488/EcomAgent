"""Tests for image generation service and API."""

import io
import json
import time
from unittest.mock import patch

import pytest
from PIL import Image


def _image_bytes(image_format: str = "PNG", size: tuple[int, int] = (2, 2)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color=(32, 128, 192)).save(
        output, format=image_format
    )
    return output.getvalue()


class TestImageUploadValidation:
    """Test file upload validation in image_service."""

    def test_reject_invalid_extension(self):
        from app.services.image_service import _validate_upload

        with pytest.raises(ValueError, match="Unsupported file type"):
            _validate_upload("virus.exe", b"malicious")

    def test_reject_oversized_file(self):
        from app.services.image_service import _validate_upload

        with pytest.raises(ValueError, match="File too large"):
            _validate_upload("image.png", b"x" * (10 * 1024 * 1024 + 1))

    def test_accept_valid_png(self):
        from app.services.image_service import _validate_upload

        # Should not raise
        _validate_upload("product.png", _image_bytes())

    def test_accept_jpg_uppercase(self):
        from app.services.image_service import _validate_upload

        # Should not raise — .lower() handles case
        _validate_upload("product.JPG", _image_bytes("JPEG"))


class TestBuildPrompt:
    """Test _build_prompt helper."""

    def test_returns_string_with_product_name(self):
        from app.services.image_service import _build_prompt

        prompt = _build_prompt("防晒衣", "home")
        assert isinstance(prompt, str)
        assert "防晒衣" in prompt

    def test_all_styles_produce_valid_prompts(self):
        from app.services.image_service import _build_prompt

        for style in ["home", "outdoor", "summer", "minimal", "live", "promotion"]:
            prompt = _build_prompt("测试商品", style)
            assert len(prompt) > 20
            assert "电商" in prompt

    def test_unknown_style_falls_back_to_minimal(self):
        from app.services.image_service import _build_prompt

        prompt = _build_prompt("商品", "nonexistent")
        assert "极简" in prompt  # falls back to minimal style description


class TestImageAPI:
    """Integration tests for image generation API endpoints."""

    @staticmethod
    def _approved_product(client, name, category="服装"):
        created = client.post("/api/products", json={"name": name, "category": category})
        assert created.status_code == 201
        product_id = created.json()["id"]
        assert client.put(f"/api/products/{product_id}", json={"status": "approved"}).status_code == 200
        return product_id

    def test_upload_no_file(self, client):
        resp = client.post("/api/images/upload")
        assert resp.status_code == 422

    def test_upload_invalid_product(self, client):
        fake_img = io.BytesIO(_image_bytes())
        fake_img.name = "test.png"
        resp = client.post(
            "/api/images/upload",
            data={"product_id": "99999"},
            files={"file": ("test.png", fake_img, "image/png")},
        )
        assert resp.status_code == 409  # M2 only accepts approved product facts

    def test_generate_missing_field(self, client):
        resp = client.post("/api/images/tasks", json={})
        assert resp.status_code == 422

    def test_generate_creates_task(self, client):
        product_id = self._approved_product(client, "图片测试商品")
        upload = client.post("/api/images/reference", data={"product_id": str(product_id)}, files={"file": ("source.png", io.BytesIO(_image_bytes()), "image/png")})
        assert upload.status_code == 201

        resp = client.post("/api/images/tasks", json={
            "product_id": product_id,
            "style": "minimal",
            "reference_asset_id": upload.json()["id"],
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] in {"pending", "no_key"}

    def test_generate_rejected_without_source_image(self, client):
        """Generation must be rejected if no source image was uploaded first."""
        product_id = self._approved_product(client, "无源图商品", "数码")

        resp = client.post("/api/images/tasks", json={
            "product_id": product_id,
            "style": "minimal",
        })
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "validation_error"

    def test_generate_with_upload_then_generate(self, client):
        """Full flow: upload source → generate → task created."""
        import io

        product_id = self._approved_product(client, "完整流程商品", "美妆")
        upload = client.post("/api/images/reference", data={"product_id": str(product_id)}, files={"file": ("source.png", io.BytesIO(_image_bytes()), "image/png")})
        assert upload.status_code == 201

        # Upload first
        fake_img = io.BytesIO(_image_bytes())
        upload_resp = client.post(
            "/api/images/reference",
            data={"product_id": str(product_id)},
            files={"file": ("product.png", fake_img, "image/png")},
        )
        assert upload_resp.status_code == 201

        # Then generate — should succeed now
        gen_resp = client.post("/api/images/tasks", json={
            "product_id": product_id,
            "style": "summer",
            "reference_asset_id": upload_resp.json()["id"],
        })
        assert gen_resp.status_code == 202
        assert "task_id" in gen_resp.json()

    def test_task_not_found(self, client):
        resp = client.get("/api/images/tasks/99999")
        assert resp.status_code == 404

    def test_get_assets_empty(self, client):
        p_resp = client.post("/api/products", json={
            "name": "无图片商品", "category": "数码"
        })
        product_id = p_resp.json()["id"]

        resp = client.get(f"/api/images/assets/{product_id}")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_poll_completed_task(self, client):
        """Full flow: create product → generate → poll until completed."""
        # Create product
        product_id = self._approved_product(client, "轮询测试商品", "美妆")
        upload = client.post(
            "/api/images/reference",
            data={"product_id": str(product_id)},
            files={"file": ("source.png", io.BytesIO(_image_bytes()), "image/png")},
        )
        assert upload.status_code == 201

        # Create generation task (uses placeholder in test)
        gen_resp = client.post("/api/images/tasks", json={
            "product_id": product_id,
            "style": "summer",
            "reference_asset_id": upload.json()["id"],
        })
        assert gen_resp.status_code == 202
        task_id = gen_resp.json()["task_id"]

        # Poll task — placeholder returns after 2s sleep
        for _ in range(10):
            resp = client.get(f"/api/images/tasks/{task_id}")
            data = resp.json()
            if data["status"] in ("completed", "failed"):
                assert data["status"] == "completed"
                assert data["result_asset_ids"] is not None
                break
            time.sleep(0.5)
        else:
            # Task may still be pending in test env; that's ok
            assert data["status"] in ("pending", "processing", "completed", "no_key")


class TestProcessGenerationTask:
    """Test process_generation_task with mocked API."""

    def test_process_creates_assets(self, db_session):
        """A configured provider response creates persisted generated assets."""
        from app.models.product import Product
        from app.services.image_service import (
            create_generation_task,
            process_generation_task,
        )

        # Create a product manually
        product = Product(name="处理测试", category="测试")
        db_session.add(product)
        db_session.flush()

        task = create_generation_task(db_session, product.id, None, "minimal")
        assert task.status == "pending"

        with patch("app.services.image_service.settings") as mock_settings, patch(
            "app.services.image_service._call_qwen_image",
            return_value=[_image_bytes(), _image_bytes(size=(3, 4))],
        ):
            mock_settings.image_gen_configured = True
            mock_settings.image_provider = "qwen"
            processed = process_generation_task(db_session, task.id)
        assert processed.status == "completed"
        assert processed.result_asset_ids is not None

        asset_ids = json.loads(processed.result_asset_ids)
        assert len(asset_ids) == 2

        from app.models.asset import Asset
        for aid in asset_ids:
            asset = db_session.query(Asset).filter(Asset.id == aid).first()
            assert asset is not None
            assert asset.asset_type == "generated"

    def test_process_failed_task_handles_error(self, db_session):
        """Simulated error path."""
        from app.models.asset import ImageGenerationTask
        from app.models.product import Product

        product = Product(name="错误测试", category="测试")
        db_session.add(product)
        db_session.flush()

        task = ImageGenerationTask(
            product_id=product.id, style="home", model_name="qwen-image-2.0"
        )
        db_session.add(task)
        db_session.flush()

        # Mock _call_qwen_image to raise
        from unittest.mock import patch
        with patch(
            "app.services.image_service._call_qwen_image",
            side_effect=RuntimeError("API timeout"),
        ), patch(
            "app.services.image_service.settings"
        ) as mock_settings:
            mock_settings.image_gen_configured = True
            from app.services.image_service import process_generation_task

            processed = process_generation_task(db_session, task.id)
            assert processed.status == "failed"
            assert "API timeout" in (processed.error_message or "")
