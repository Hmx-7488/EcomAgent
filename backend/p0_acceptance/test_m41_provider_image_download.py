"""M4.1 Provider image download, Base64 and atomic-save contracts."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.models.asset import ImageGenerationTask
from app.services import image_integrity, image_service
from scripts.image_fixture import png_bytes


class _StreamResponse:
    def __init__(
        self,
        status_code: int,
        *,
        payload: bytes = b"",
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://provider.example/image")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "download failed", request=request, response=response
            )

    def iter_bytes(self):
        midpoint = max(1, len(self._payload) // 2)
        yield self._payload[:midpoint]
        yield self._payload[midpoint:]


class _FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requested_urls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    @contextmanager
    def stream(self, _method, url, headers=None):
        del headers
        self.requested_urls.append(url)
        yield next(self.responses)


def _client_factory(monkeypatch, responses):
    client = _FakeClient(responses)
    monkeypatch.setattr(
        image_integrity.httpx,
        "Client",
        lambda **_kwargs: client,
    )
    return client


def test_https_download_allows_one_bounded_redirect_and_validates_image(
    monkeypatch,
):
    payload = png_bytes(6, 7)
    client = _client_factory(
        monkeypatch,
        [
            _StreamResponse(302, headers={"location": "/final.png"}),
            _StreamResponse(
                200,
                payload=payload,
                headers={
                    "content-type": "text/plain",
                    "content-length": str(len(payload)),
                },
            ),
        ],
    )
    assert (
        image_integrity.download_https_image(
            "https://provider.example/temporary/result"
        )
        == payload
    )
    assert client.requested_urls == [
        "https://provider.example/temporary/result",
        "https://provider.example/final.png",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://provider.example/result.png",
        "https://localhost/result.png",
        "https://127.0.0.1/result.png",
    ],
)
def test_provider_download_rejects_non_https_and_local_targets(url):
    with pytest.raises(ValueError):
        image_integrity.download_https_image(url)


def test_provider_download_rejects_declared_oversize(monkeypatch):
    _client_factory(
        monkeypatch,
        [
            _StreamResponse(
                200,
                payload=png_bytes(),
                headers={
                    "content-length": str(image_integrity.MAX_FILE_SIZE + 1)
                },
            )
        ],
    )
    with pytest.raises(RuntimeError):
        image_integrity.download_https_image(
            "https://provider.example/result.png"
        )


def test_provider_download_rejects_streamed_oversize(monkeypatch):
    monkeypatch.setattr(image_integrity, "MAX_FILE_SIZE", 32)
    _client_factory(
        monkeypatch,
        [_StreamResponse(200, payload=b"x" * 33)],
    )
    with pytest.raises(RuntimeError):
        image_integrity.download_https_image(
            "https://provider.example/result.png"
        )


def test_provider_download_rejects_excessive_redirects(monkeypatch):
    _client_factory(
        monkeypatch,
        [
            _StreamResponse(302, headers={"location": "/one"}),
            _StreamResponse(302, headers={"location": "/two"}),
            _StreamResponse(302, headers={"location": "/three"}),
        ],
    )
    with pytest.raises(RuntimeError):
        image_integrity.download_https_image(
            "https://provider.example/start"
        )


def test_provider_download_rejects_url_extension_mismatch(monkeypatch):
    _client_factory(
        monkeypatch,
        [_StreamResponse(200, payload=png_bytes())],
    )
    with pytest.raises(RuntimeError):
        image_integrity.download_https_image(
            "https://provider.example/result.jpg"
        )


def test_provider_download_preserves_timeout_category(monkeypatch):
    class TimeoutClient(_FakeClient):
        @contextmanager
        def stream(self, _method, _url, headers=None):
            del headers
            raise httpx.ReadTimeout("offline timeout")
            yield

    monkeypatch.setattr(
        image_integrity.httpx,
        "Client",
        lambda **_kwargs: TimeoutClient([]),
    )
    with pytest.raises(httpx.TimeoutException):
        image_integrity.download_https_image(
            "https://provider.example/result.png"
        )

def test_qwen_adapter_downloads_temporary_url_instead_of_returning_it(
    monkeypatch, db_session, tmp_path
):
    from app.models.product import Product

    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_service.settings,
        "image_gen_api_base",
        "https://dashscope.example/api/v1",
    )
    monkeypatch.setattr(image_service.settings, "image_gen_api_key", "test-only")
    product = Product(name="Qwen fixture", category="Demo", status="approved")
    db_session.add(product)
    db_session.flush()
    reference = image_service.save_upload(
        db_session,
        product.id,
        png_bytes(),
        "reference.png",
    )
    task = image_service.create_generation_task(
        db_session,
        product.id,
        reference.id,
        "minimal",
    )
    provider_response = Mock()
    provider_response.raise_for_status.return_value = None
    provider_response.json.return_value = {
        "output": {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"image": "https://provider.example/one.png"},
                            {"image": "https://provider.example/two.png"},
                            {"image": "https://provider.example/three.png"},
                        ]
                    }
                }
            ]
        }
    }
    monkeypatch.setattr(
        image_service.httpx,
        "post",
        lambda *_args, **_kwargs: provider_response,
    )
    payload = png_bytes(9, 10)
    calls: list[str] = []

    def download(url):
        calls.append(url)
        return payload

    monkeypatch.setattr(image_service, "download_https_image", download)
    assert image_service._call_qwen_image(db_session, task) == [payload] * 3
    assert calls == [
        "https://provider.example/one.png",
        "https://provider.example/two.png",
        "https://provider.example/three.png",
    ]

def test_google_base64_result_uses_unified_validation(
    monkeypatch, db_session, tmp_path
):
    from app.models.asset import Asset
    from app.models.product import Product

    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(tmp_path))
    product = Product(name="Google fixture", category="Demo", status="approved")
    db_session.add(product)
    db_session.flush()
    reference_bytes = png_bytes()
    reference = image_service.save_upload(
        db_session,
        product.id,
        reference_bytes,
        "reference.png",
    )
    task = ImageGenerationTask(
        product_id=product.id,
        source_asset_id=reference.id,
        style="minimal",
        prompt="safe",
    )
    db_session.add(task)
    db_session.commit()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "output_image": {
            "data": base64.b64encode(png_bytes(11, 12)).decode("ascii")
        }
    }
    monkeypatch.setattr(image_service.httpx, "post", lambda *_args, **_kwargs: response)
    result = image_service._call_google_gemini_image(db_session, task)
    info = image_service.validate_image_bytes(result[0])
    assert (info.width, info.height) == (11, 12)


def test_google_invalid_base64_does_not_create_generated_asset(
    monkeypatch, db_session, tmp_path
):
    from app.models.asset import Asset
    from app.models.product import Product

    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(tmp_path))
    product = Product(name="Google invalid", category="Demo", status="approved")
    db_session.add(product)
    db_session.flush()
    reference = image_service.save_upload(
        db_session,
        product.id,
        png_bytes(),
        "reference.png",
    )
    task = image_service.create_generation_task(
        db_session, product.id, reference.id, "minimal"
    )
    monkeypatch.setattr(image_service.settings, "image_provider", "google")
    monkeypatch.setattr(image_service.settings, "google_api_key", "test-only")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"output_image": {"data": "%%%invalid%%%"}}
    monkeypatch.setattr(image_service.httpx, "post", lambda *_args, **_kwargs: response)
    processed = image_service.process_generation_task(db_session, task.id)
    assert processed.status == "failed"
    assert (
        db_session.query(Asset)
        .filter(Asset.product_id == product.id, Asset.asset_type == "generated")
        .count()
        == 0
    )
    assert sum(1 for path in tmp_path.rglob("*") if path.is_file()) == 1
    assert not any(path.name.endswith(".part") for path in tmp_path.rglob("*"))


def test_database_failure_removes_atomically_saved_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(tmp_path))
    db = SimpleNamespace(
        add=Mock(),
        commit=Mock(side_effect=RuntimeError("database unavailable")),
        rollback=Mock(),
        refresh=Mock(),
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        image_service.save_upload(
            db,
            1,
            png_bytes(),
            "reference.png",
        )
    db.rollback.assert_called_once()
    assert not any(path.is_file() for path in tmp_path.rglob("*"))
