"""Official qwen-image-2.0 synchronous multimodal contract tests.

All HTTP and image-download boundaries are mocked. These tests must never
reach DashScope or any other external network.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image

from app.core.config import Settings, settings
from app.models.asset import Asset, ImageGenerationTask
from app.models.content import ApprovalRecord, AuditEvent
from app.models.product import Product
from app.models.user import User
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
_UNSET = object()


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


def _http_status_diagnostic(
    *,
    headers: dict[str, str] | None = None,
    json_body: object = _UNSET,
    content: bytes = b"",
) -> str:
    request = httpx.Request("POST", API_BASE + OFFICIAL_PATH)
    response_kwargs: dict[str, object] = {
        "request": request,
        "headers": headers or {},
    }
    if json_body is _UNSET:
        response_kwargs["content"] = content
    else:
        response_kwargs["json"] = json_body
    response = httpx.Response(403, **response_kwargs)
    error = httpx.HTTPStatusError(
        "provider failure details must not be retained",
        request=request,
        response=response,
    )
    return image_service._provider_http_diagnostic(error, elapsed_ms=17)


def _create_task(
    db_session,
    monkeypatch,
    tmp_path,
    *,
    reference_bytes: bytes | None = None,
    reference_filename: str = "reference.png",
):
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
    reference_bytes = reference_bytes or png_bytes(12, 10)
    reference = image_service.save_upload(
        db_session,
        product.id,
        reference_bytes,
        reference_filename,
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
    assert "json" not in posted
    assert isinstance(posted["content"], bytes)
    assert len(posted["content"]) <= image_service.QWEN_MAX_REQUEST_BODY_BYTES
    body = json.loads(posted["content"])
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
    assert image_data_url.startswith("data:image/jpeg;base64,")
    encoded_reference = base64.b64decode(
        image_data_url.split(",", 1)[1],
        validate=True,
    )
    with Image.open(io.BytesIO(encoded_reference)) as encoded_image:
        assert encoded_image.format == "JPEG"
        assert encoded_image.size == (12, 10)
        encoded_image.load()
    assert message["content"][1] == {"text": task.prompt}
    assert downloads == [
        "https://provider.example/one.png",
        "https://provider.example/two.png",
        "https://provider.example/three.png",
    ]
    assert len(payloads) == 3


def test_qwen_compresses_large_reference_below_request_body_limit(
    db_session, monkeypatch, tmp_path
):
    source = io.BytesIO()
    Image.effect_noise((1254, 1254), 100).convert("RGB").save(
        source,
        format="BMP",
    )
    task, _reference = _create_task(
        db_session,
        monkeypatch,
        tmp_path,
        reference_bytes=source.getvalue(),
        reference_filename="reference.bmp",
    )
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted.update({"url": url, **kwargs})
        return _response_with_images(
            "https://provider.example/one.png",
            "https://provider.example/two.png",
            "https://provider.example/three.png",
        )

    monkeypatch.setattr(image_service.httpx, "post", fake_post)
    monkeypatch.setattr(
        image_service,
        "download_https_image",
        lambda _url: png_bytes(),
    )

    image_service._call_qwen_image(db_session, task)

    assert len(posted["content"]) <= image_service.QWEN_MAX_REQUEST_BODY_BYTES
    body = json.loads(posted["content"])
    image_data_url = body["input"]["messages"][0]["content"][0]["image"]
    encoded_reference = base64.b64decode(image_data_url.split(",", 1)[1])
    with Image.open(io.BytesIO(encoded_reference)) as encoded_image:
        assert encoded_image.format == "JPEG"
        assert max(encoded_image.size) <= image_service.QWEN_REFERENCE_MAX_EDGE


def test_qwen_rejects_oversized_request_before_http_post(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(
        image_service,
        "_reference_image_data_url",
        lambda *_args: (
            "data:image/jpeg;base64,"
            + "A" * image_service.QWEN_MAX_REQUEST_BODY_BYTES
        ),
    )
    post = Mock()
    monkeypatch.setattr(image_service.httpx, "post", post)

    with pytest.raises(image_service.ProviderFailedError, match="safe transport limit"):
        image_service._call_qwen_image(db_session, task)

    post.assert_not_called()


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
    response = httpx.Response(
        403,
        request=request,
        headers={"x-request-id": "req-safe-123"},
        json={
            "code": "WorkspaceMismatch",
            "message": f"must not leak {API_KEY} or {API_BASE}",
        },
    )
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
    with pytest.raises(image_service.ProviderFailedError) as error:
        image_service._call_qwen_image(db_session, task)
    message = str(error.value)
    assert "type=http_status_error" in message
    assert "http_status=403" in message
    assert "provider_code=WorkspaceMismatch" in message
    assert "request_id=req-safe-123" in message
    assert "elapsed_ms=" in message
    assert API_KEY not in message
    assert API_BASE not in message
    assert "must not leak" not in message


def test_qwen_http_diagnostic_uses_top_level_json_request_id():
    message = _http_status_diagnostic(
        json_body={
            "code": "WorkspaceMismatch",
            "request_id": "json.req_123-ABC",
            "message": (
                f"must not leak {API_KEY}, {API_BASE}, "
                "data:image/png;base64,secret or "
                "https://provider.example/private/result.png"
            ),
        }
    )

    assert message == (
        "Qwen image request failed: type=http_status_error "
        "http_status=403 elapsed_ms=17 "
        "provider_code=WorkspaceMismatch request_id=json.req_123-ABC"
    )


def test_qwen_http_diagnostic_prefers_valid_trusted_header_over_json():
    message = _http_status_diagnostic(
        headers={"x-request-id": "header.req_123"},
        json_body={
            "code": "WorkspaceMismatch",
            "request_id": "json.req_456",
        },
    )

    assert "request_id=header.req_123" in message
    assert "json.req_456" not in message


def test_qwen_http_diagnostic_falls_back_from_invalid_header_to_json():
    message = _http_status_diagnostic(
        headers={"x-request-id": "https://provider.example/private/request"},
        json_body={
            "code": "WorkspaceMismatch",
            "request_id": "json.req_456",
        },
    )

    assert "request_id=json.req_456" in message
    assert "provider.example" not in message


def test_qwen_http_diagnostic_uses_next_valid_trusted_header():
    message = _http_status_diagnostic(
        headers={
            "x-request-id": "https://provider.example/private/request",
            "request-id": "secondary.header_123",
        },
        json_body={
            "code": "WorkspaceMismatch",
            "request_id": "json.req_456",
        },
    )

    assert "request_id=secondary.header_123" in message
    assert "json.req_456" not in message
    assert "provider.example" not in message


def test_qwen_http_diagnostic_ignores_unlisted_request_id_header():
    message = _http_status_diagnostic(
        headers={"request_id": "untrusted-header-value"},
        json_body={"code": "WorkspaceMismatch"},
    )

    assert "request_id=" not in message
    assert "untrusted-header-value" not in message


@pytest.mark.parametrize(
    "candidate",
    [
        pytest.param("request*id", id="asterisk"),
        pytest.param("request&id", id="ampersand"),
        pytest.param("request@id", id="at-sign"),
        pytest.param("request%id", id="percent"),
        pytest.param("request\tid", id="tab"),
        pytest.param("request\rid", id="carriage-return"),
        pytest.param("request\nid", id="line-feed"),
        pytest.param("request\0id", id="nul"),
        pytest.param("请求编号", id="non-ascii"),
    ],
)
def test_qwen_http_diagnostic_rejects_additional_disallowed_request_id_characters(
    candidate,
):
    message = _http_status_diagnostic(
        json_body={"code": "WorkspaceMismatch", "request_id": candidate}
    )

    assert "request_id=" not in message
    assert candidate not in message


def test_qwen_http_diagnostic_accepts_request_id_at_exact_length_limit():
    candidate = "a" * 96

    message = _http_status_diagnostic(
        json_body={"code": "WorkspaceMismatch", "request_id": candidate}
    )

    assert f"request_id={candidate}" in message


@pytest.mark.parametrize(
    ("header_name", "candidate"),
    [
        pytest.param("x-trace-id", "xtrace.req_123", id="x-trace-id"),
        pytest.param("trace-id", "trace.req_456", id="trace-id"),
    ],
)
def test_qwen_http_diagnostic_extracts_each_trusted_trace_header(
    header_name, candidate
):
    message = _http_status_diagnostic(
        headers={header_name: candidate},
        json_body={"code": "WorkspaceMismatch"},
    )

    assert f"request_id={candidate}" in message


@pytest.mark.parametrize("location", ["header", "json"])
@pytest.mark.parametrize(
    "candidate",
    [
        "https://provider.example/request/123",
        "trace:123",
        "path/to/request",
        r"path\to\request",
        "request?id=123",
        " request-123 ",
        "a" * 97,
    ],
)
def test_qwen_http_diagnostic_rejects_entire_unsafe_request_id(
    location, candidate
):
    headers = {"x-request-id": candidate} if location == "header" else None
    json_body = (
        {"code": "WorkspaceMismatch", "request_id": candidate}
        if location == "json"
        else {"code": "WorkspaceMismatch"}
    )

    message = _http_status_diagnostic(headers=headers, json_body=json_body)

    assert "request_id=" not in message
    assert candidate not in message


@pytest.mark.parametrize(
    "json_body",
    [
        ["request_id", "nested.req_123"],
        {"error": {"request_id": "nested.req_123"}},
        {"request_id": 12345},
        {"request_id": None},
        {"request_id": ""},
    ],
)
def test_qwen_http_diagnostic_rejects_non_top_level_string_request_id(
    json_body
):
    message = _http_status_diagnostic(json_body=json_body)

    assert "request_id=" not in message
    assert "nested.req_123" not in message


def test_qwen_http_diagnostic_safely_ignores_non_json_body():
    message = _http_status_diagnostic(
        content=(
            f"not-json request_id=unsafe {API_KEY} {API_BASE} "
            "https://provider.example/private/result.png"
        ).encode()
    )

    assert message == (
        "Qwen image request failed: type=http_status_error "
        "http_status=403 elapsed_ms=17"
    )


def test_qwen_http_failure_persists_only_safe_diagnostic_without_retry(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    request = httpx.Request("POST", API_BASE + OFFICIAL_PATH)
    response = httpx.Response(
        403,
        request=request,
        json={
            "code": "WorkspaceMismatch",
            "request_id": "json.req_789",
            "message": (
                f"must not leak {API_KEY}, {API_BASE}, "
                "data:image/png;base64,secret or "
                "https://provider.example/private/result.png"
            ),
            "request": {"image": "data:image/png;base64,secret"},
        },
    )
    provider_response = Mock()
    provider_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "provider failed with private response details",
        request=request,
        response=response,
    )
    post = Mock(return_value=provider_response)
    monkeypatch.setattr(image_service.httpx, "post", post)

    processed = image_service.process_generation_task(db_session, task.id)

    assert post.call_count == 1
    assert processed.status == "failed"
    assert processed.retry_count == 0
    assert processed.result_asset_ids is None
    assert "http_status=403" in processed.error_message
    assert "provider_code=WorkspaceMismatch" in processed.error_message
    assert "request_id=json.req_789" in processed.error_message
    assert (
        db_session.query(Asset)
        .filter(Asset.asset_type == "generated")
        .count()
        == 0
    )
    for forbidden in (
        API_KEY,
        API_BASE,
        "must not leak",
        "provider.example",
        "data:image",
        "private response details",
    ):
        assert forbidden not in processed.error_message


def test_provider_failure_task_cannot_enter_confirmation_or_approval_flow(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    actor = User(
        username="failed-task-operator",
        password_hash="not-used",
        role=ROLE_OPERATOR_CONTENT,
    )
    db_session.add(actor)
    db_session.commit()
    db_session.refresh(actor)
    provider = Mock(
        side_effect=image_service.ProviderFailedError("safe provider failure")
    )
    monkeypatch.setattr(
        image_service,
        "generate_image_with_provider",
        provider,
    )

    processed = image_service.process_generation_task(db_session, task.id)

    with pytest.raises(RuntimeError, match="completed_image_required"):
        image_service.confirm_task(db_session, actor, processed)
    with pytest.raises(RuntimeError, match="illegal_status_transition"):
        image_service.transition_task(
            db_session,
            actor,
            processed,
            "submit",
        )

    db_session.expire_all()
    persisted = db_session.get(ImageGenerationTask, task.id)
    assert provider.call_count == 1
    assert persisted.status == "failed"
    assert persisted.retry_count == 0
    assert persisted.result_asset_ids is None
    assert persisted.confirmed_at is None
    assert persisted.approval_status == "draft"
    assert (
        db_session.query(Asset)
        .filter(
            Asset.product_id == task.product_id,
            Asset.asset_type == "generated",
        )
        .count()
        == 0
    )
    assert (
        db_session.query(ApprovalRecord)
        .filter(
            ApprovalRecord.target_type == "image_task",
            ApprovalRecord.target_id == task.id,
        )
        .count()
        == 0
    )


def test_qwen_maps_connect_error_to_safe_diagnostic(
    db_session, monkeypatch, tmp_path
):
    task, _reference = _create_task(db_session, monkeypatch, tmp_path)
    request = httpx.Request("POST", API_BASE + OFFICIAL_PATH)
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        Mock(side_effect=httpx.ConnectError("secret connection detail", request=request)),
    )

    with pytest.raises(image_service.ProviderFailedError) as error:
        image_service._call_qwen_image(db_session, task)

    message = str(error.value)
    assert "type=connect_error" in message
    assert "elapsed_ms=" in message
    assert "secret connection detail" not in message
    assert API_BASE not in message


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
