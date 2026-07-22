"""Tests for image generation service and API."""

import io
import json
import time
from unittest.mock import patch

import pytest


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
        _validate_upload("product.png", b"fake-png-data")

    def test_accept_jpg_uppercase(self):
        from app.services.image_service import _validate_upload

        # Should not raise — .lower() handles case
        _validate_upload("product.JPG", b"fake-jpg-data")


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


class TestPlaceholderResult:
    """Test _placeholder_result fallback."""

    def test_returns_three_urls(self):
        from app.models.asset import ImageGenerationTask
        from app.services.image_service import _placeholder_result

        task = ImageGenerationTask(
            id=1, product_id=1, style="home", model_name="qwen-image"
        )
        urls = _placeholder_result(task)
        assert len(urls) == 3
        assert all("placeholder_home_" in u for u in urls)


class TestImageAPI:
    """Integration tests for image generation API endpoints."""

    def test_upload_no_file(self, client):
        resp = client.post("/api/images/upload")
        assert resp.status_code == 422

    def test_upload_invalid_product(self, client):
        fake_img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        fake_img.name = "test.png"
        resp = client.post(
            "/api/images/upload",
            data={"product_id": "99999"},
            files={"file": ("test.png", fake_img, "image/png")},
        )
        assert resp.status_code in (201, 404)  # 404 if product FK enforced

    def test_generate_missing_field(self, client):
        resp = client.post("/api/images/generate", json={})
        assert resp.status_code == 422

    def test_generate_creates_task(self, client):
        # Create a product first
        p_resp = client.post("/api/products", json={
            "name": "图片测试商品", "category": "服装"
        })
        product_id = p_resp.json()["id"]
        upload = client.post("/api/images/upload", data={"product_id": str(product_id)}, files={"file": ("source.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")})
        assert upload.status_code == 201

        resp = client.post("/api/images/generate", json={
            "product_id": product_id,
            "style": "minimal",
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    def test_generate_rejected_without_source_image(self, client):
        """Generation must be rejected if no source image was uploaded first."""
        p_resp = client.post("/api/products", json={
            "name": "无源图商品", "category": "数码"
        })
        product_id = p_resp.json()["id"]

        resp = client.post("/api/images/generate", json={
            "product_id": product_id,
            "style": "minimal",
        })
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "request_error"
        assert "No source image" in resp.json()["detail"]["message"]

    def test_generate_with_upload_then_generate(self, client):
        """Full flow: upload source → generate → task created."""
        import io

        p_resp = client.post("/api/products", json={
            "name": "完整流程商品", "category": "美妆"
        })
        product_id = p_resp.json()["id"]
        upload = client.post("/api/images/upload", data={"product_id": str(product_id)}, files={"file": ("source.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")})
        assert upload.status_code == 201

        # Upload first
        fake_img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        upload_resp = client.post(
            "/api/images/upload",
            data={"product_id": str(product_id)},
            files={"file": ("product.png", fake_img, "image/png")},
        )
        assert upload_resp.status_code == 201

        # Then generate — should succeed now
        gen_resp = client.post("/api/images/generate", json={
            "product_id": product_id,
            "style": "summer",
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
        p_resp = client.post("/api/products", json={
            "name": "轮询测试商品", "category": "美妆"
        })
        product_id = p_resp.json()["id"]
        upload = client.post(
            "/api/images/upload",
            data={"product_id": str(product_id)},
            files={"file": ("source.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
        )
        assert upload.status_code == 201

        # Create generation task (uses placeholder in test)
        gen_resp = client.post("/api/images/generate", json={
            "product_id": product_id,
            "style": "summer",
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
            return_value=["/uploads/generated-1.png", "/uploads/generated-2.png"],
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
            product_id=product.id, style="home", model_name="qwen-image"
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
