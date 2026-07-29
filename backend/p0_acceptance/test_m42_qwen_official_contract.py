"""Official qwen-image-2.0 synchronous multimodal contract tests.

All HTTP and image-download boundaries are mocked. These tests must never
reach DashScope or any other external network.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from app.core.config import Settings, settings
from app.models.asset import Asset, ImageGenerationTask
from app.models.content import AuditEvent
from app.models.product import Product
from app.services import image_service
from scripts.image_fixture import png_bytes

from .helpers import (
    IMAGE_REFERENCE_PATH,
    IMAGE_TASKS_PATH,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    create_approved_product,
    login_as,
)


API_BASE = "https://test-workspace.cn-beijing.maas.aliyuncs.com/api/v1"
API_KEY = "test-only-qwen-key"
MODEL = "qwen-image-2.0"
OFFICIAL_PATH = "/services/aigc/multimodal-generation/generation"


def _response_with_images(*urls: str) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "output": {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": [{"image": url} for url in urls],
                    },
                }
            ]
        }
    }
    return response


def _create_task(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "image_provider", "qwen")
    monkeypatch.setattr(settings, "image_gen_api_base", API_BASE)
    monkeypatch.setattr(settings, "image_gen_api_key", API_KEY)
    monkeypatch.setattr(settings, "image_gen_model", MODEL)
    monkeypatch.setattr(settings, "image_gen_output_count", 3)

    product = Product(
        name="Qwen contract fixture",
        category="Demo",
        status="approved",
    )
    db_session.add(product)
    db_session.commit()
    reference_bytes = png_bytes(12, 10)
    reference = image_service.save_upload(
        db_session,
        product.id,
        reference_bytes,
        "reference.png",
    )
    task = image_service.create_generation_task(
        db_session,
        product.id,
        reference.id,
        "minimal",
    )
    return task, reference_bytes


def test_image_settings_and_task_record_the_actual_configured_model(
    db_session, monkeypatch, tmp_path
):
    assert settings.image_gen_model == "qwen-image-2.0"
    assert settings.image_gen_output_count == 3
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    assert task.model_name == MODEL


def test_p0_output_count_is_fixed_to_three():
    with pytest.raises(ValueError):
        Settings(image_gen_output_count=2)


def test_p0_accepts_beijing_workspace_image_api_base():
    configured = Settings(image_gen_api_base=API_BASE)
    assert configured.image_gen_api_base == API_BASE


def test_p0_rejects_legacy_public_dashscope_image_api_base():
    with pytest.raises(ValueError, match="legacy public DashScope"):
        Settings(image_gen_api_base="https://dashscope.aliyuncs.com/api/v1")


def test_p0_rejects_non_https_image_api_base():
    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(
            image_gen_api_base=(
                "http://test-workspace.cn-beijing.maas.aliyuncs.com/api/v1"
            )
        )


def test_p0_rejects_non_beijing_workspace_image_api_base():
    with pytest.raises(ValueError, match="cn-beijing Workspace-specific"):
        Settings(
            image_gen_api_base=(
                "https://test-workspace.cn-shanghai.maas.aliyuncs.com/api/v1"
            )
        )


def test_p0_rejects_non_qwen_image_2_model():
    with pytest.raises(ValueError, match="must be qwen-image-2.0"):
        Settings(image_gen_model="qwen-image")


def test_qwen_request_matches_official_multimodal_contract_and_includes_reference(
    db_session, monkeypatch, tmp_path
):
    task, reference_bytes = _create_task(db_session, monkeypatch, tmp_path)
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted.update({"url": url, **kwargs})
        return _response_with_images(
            "https://provider.example/one.png",
            "https://provider.example/two.png",
            "https://provider.example/three.png",
        )

    monkeypatch.setattr(image_service.httpx, "post", fake_post)
    downloads: list[str] = []

    def fake_download(url: str) -> bytes:
        downloads.append(url)
        return png_bytes(20 + len(downloads), 18)

    monkeypatch.setattr(image_service, "download_https_image", fake_download)
    payloads = image_service._call_qwen_image(db_session, task)

    assert posted["url"] == API_BASE + OFFICIAL_PATH
    assert posted["headers"] == {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    body = posted["json"]
    assert body["model"] == MODEL
    assert body["parameters"] == {
        "n": 3,
        "size": "1024*1024",
        "watermark": False,
    }
    assert len(body["input"]["messages"]) == 1
    message = body["input"]["messages"][0]
    assert message["role"] == "user"
    assert len(message["content"]) == 2
    image_data_url = message["content"][0]["image"]
    assert image_data_url.startswith("data:image/png;base64,")
    assert base64.b64decode(image_data_url.split(",", 1)[1], validate=True) == reference_bytes
    assert message["content"][1] == {"text": task.prompt}
    assert downloads == [
        "https://provider.example/one.png",
        "https://provider.example/two.png",
        "https://provider.example/three.png",
    ]
    assert len(payloads) == 3


@pytest.mark.parametrize(
    "provider_payload",
    [
        {"output": {"choices": []}},
        {"output": {}},
        {
            "output": {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"text": "not an image"},
                                {"image": ""},
                            ]
                        }
                    }
                ]
            }
        },
    ],
)
def test_qwen_rejects_empty_choices_and_missing_images(
    provider_payload, db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = provider_payload
    monkeypatch.setattr(image_service.httpx, "post", lambda *_a, **_kw: response)
    with pytest.raises(image_service.ProviderFieldMissingError):
        image_service._call_qwen_image(db_session, task)


def test_qwen_rejects_partial_results_before_any_download(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        lambda *_a, **_kw: _response_with_images(
            "https://provider.example/one.png",
            "https://provider.example/two.png",
        ),
    )
    download = Mock(return_value=png_bytes())
    monkeypatch.setattr(image_service, "download_https_image", download)
    with pytest.raises(image_service.ProviderFieldMissingError):
        image_service._call_qwen_image(db_session, task)
    download.assert_not_called()


def test_qwen_maps_request_timeout_to_safe_timeout(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        Mock(side_effect=httpx.ReadTimeout("offline timeout")),
    )
    with pytest.raises(image_service.ProviderTimeoutError):
        image_service._call_qwen_image(db_session, task)


def test_qwen_maps_http_error_to_safe_provider_failure(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    request = httpx.Request("POST", API_BASE + OFFICIAL_PATH)
    response = httpx.Response(500, request=request)
    provider_response = Mock()
    provider_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "provider failed",
        request=request,
        response=response,
    )
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        lambda *_a, **_kw: provider_response,
    )
    with pytest.raises(image_service.ProviderFailedError):
        image_service._call_qwen_image(db_session, task)


@pytest.mark.parametrize(
    "download_error",
    [
        ValueError("non-https URL"),
        RuntimeError("download failed"),
        httpx.ReadTimeout("download timeout"),
    ],
)
def test_qwen_maps_invalid_url_and_download_failures(
    download_error, db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        lambda *_a, **_kw: _response_with_images(
            "https://provider.example/one.png",
            "https://provider.example/two.png",
            "https://provider.example/three.png",
        ),
    )
    monkeypatch.setattr(
        image_service,
        "download_https_image",
        Mock(side_effect=download_error),
    )
    expected = (
        image_service.ProviderTimeoutError
        if isinstance(download_error, httpx.TimeoutException)
        else image_service.ProviderFailedError
    )
    with pytest.raises(expected):
        image_service._call_qwen_image(db_session, task)


def test_invalid_downloaded_image_never_completes_or_creates_generated_assets(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        lambda *_a, **_kw: _response_with_images(
            "https://provider.example/one.png",
            "https://provider.example/two.png",
            "https://provider.example/three.png",
        ),
    )
    payloads = iter([png_bytes(), png_bytes(), b"not-an-image"])
    monkeypatch.setattr(
        image_service,
        "download_https_image",
        lambda _url: next(payloads),
    )
    processed = image_service.process_generation_task(db_session, task.id)
    assert processed.status == "failed"
    assert processed.result_asset_ids is None
    assert (
        db_session.query(Asset)
        .filter(Asset.asset_type == "generated")
        .count()
        == 0
    )
    assert sum(1 for path in Path(tmp_path).iterdir() if path.is_file()) == 1


def test_generated_file_failure_rolls_back_rows_and_all_partial_files(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(
        image_service,
        "generate_image_with_provider",
        lambda **_kwargs: [png_bytes(21, 18), png_bytes(22, 18), png_bytes(23, 18)],
    )
    original_write = image_service.write_atomic_image
    calls = 0

    def fail_second_write(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated storage failure")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(image_service, "write_atomic_image", fail_second_write)
    processed = image_service.process_generation_task(db_session, task.id)
    assert processed.status == "failed"
    assert processed.result_asset_ids is None
    assert (
        db_session.query(Asset)
        .filter(Asset.asset_type == "generated")
        .count()
        == 0
    )
    assert sum(1 for path in Path(tmp_path).iterdir() if path.is_file()) == 1


def test_three_valid_results_are_all_saved_before_task_completes(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(
        image_service,
        "generate_image_with_provider",
        lambda **_kwargs: [png_bytes(21, 18), png_bytes(22, 18), png_bytes(23, 18)],
    )
    processed = image_service.process_generation_task(db_session, task.id)
    assert processed.status == "completed"
    asset_ids = json.loads(processed.result_asset_ids)
    assert len(asset_ids) == 3
    assert db_session.query(Asset).filter(Asset.id.in_(asset_ids)).count() == 3
    assert sum(1 for path in Path(tmp_path).iterdir() if path.is_file()) == 4

def test_reference_base64_and_key_never_enter_audit_or_logs(
    client, db_session, monkeypatch, caplog
):
    operator = login_as(
        client,
        ROLE_OPERATOR_CONTENT,
        TEST_PASSWORDS[ROLE_OPERATOR_CONTENT],
    )
    product = create_approved_product(client, operator)
    reference_bytes = png_bytes(12, 10)
    uploaded = client.post(
        IMAGE_REFERENCE_PATH,
        headers=operator,
        data={"product_id": str(product["id"])},
        files={"file": ("reference.png", reference_bytes, "image/png")},
    )
    assert uploaded.status_code == 201

    monkeypatch.setattr(settings, "image_provider", "qwen")
    monkeypatch.setattr(settings, "image_gen_api_base", API_BASE)
    monkeypatch.setattr(settings, "image_gen_api_key", API_KEY)
    monkeypatch.setattr(settings, "image_gen_model", MODEL)
    monkeypatch.setattr(settings, "image_gen_output_count", 3)
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        lambda *_a, **_kw: _response_with_images(
            "https://provider.example/one.png",
            "https://provider.example/two.png",
            "https://provider.example/three.png",
        ),
    )
    monkeypatch.setattr(
        image_service,
        "download_https_image",
        lambda _url: png_bytes(20, 18),
    )
    response = client.post(
        IMAGE_TASKS_PATH,
        headers=operator,
        json={
            "product_id": product["id"],
            "style": "minimal",
            "reference_asset_id": uploaded.json()["id"],
        },
    )
    assert response.status_code == 202

    audit_text = json.dumps(
        [
            {
                "summary": row.summary,
                "before": row.before_json,
                "after": row.after_json,
            }
            for row in db_session.query(AuditEvent).all()
        ],
        ensure_ascii=False,
    )
    reference_marker = base64.b64encode(reference_bytes).decode("ascii")[:40]
    for forbidden in (API_KEY, "data:image", reference_marker):
        assert forbidden not in audit_text
        assert forbidden not in caplog.text