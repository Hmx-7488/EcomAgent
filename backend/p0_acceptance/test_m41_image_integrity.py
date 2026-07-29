"""M4.1 image-integrity and atomic-persistence acceptance tests."""

from __future__ import annotations

import io
import os
import struct
import zlib

import pytest

from app.models.asset import Asset
from app.services import image_service

from .helpers import (
    IMAGE_REFERENCE_PATH,
    IMAGE_TASKS_PATH,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    create_approved_product,
    login_as,
)


def _chunk(name: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + name
        + payload
        + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
    )


def real_png(width: int = 2, height: int = 2) -> bytes:
    """Create a tiny, standards-compliant RGB PNG without fixture shortcuts."""

    row = b"\x00" + (b"\x20\x80\xc0" * width)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
        )
        + _chunk(b"IDAT", zlib.compress(row * height))
        + _chunk(b"IEND", b"")
    )


def _operator(client):
    return login_as(
        client,
        ROLE_OPERATOR_CONTENT,
        TEST_PASSWORDS[ROLE_OPERATOR_CONTENT],
    )


def _upload(client, headers, product_id: int, name: str, payload: bytes, mime: str):
    return client.post(
        IMAGE_REFERENCE_PATH,
        headers=headers,
        data={"product_id": str(product_id)},
        files={"file": (name, io.BytesIO(payload), mime)},
    )


def test_validate_image_bytes_decodes_verifies_and_reloads_real_png():
    info = image_service.validate_image_bytes(real_png(3, 4), filename="valid.png")
    assert info.format == "PNG"
    assert info.extension == ".png"
    assert (info.width, info.height) == (3, 4)


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("empty.png", b""),
        ("forged.png", b"not-an-image"),
        ("truncated.png", real_png()[:-8]),
        ("wrong.jpg", real_png()),
    ],
)
def test_validate_image_bytes_rejects_empty_forged_truncated_and_mismatched(
    name, payload
):
    with pytest.raises(ValueError):
        image_service.validate_image_bytes(payload, filename=name)


def test_validate_image_bytes_rejects_supported_extension_with_wrong_format():
    with pytest.raises(ValueError):
        image_service.validate_image_bytes(b"GIF89a-not-supported", filename="image.gif")


def test_validate_image_bytes_rejects_excessive_pixel_count(monkeypatch):
    monkeypatch.setattr(image_service, "MAX_IMAGE_PIXELS", 8)
    with pytest.raises(ValueError, match="pixel"):
        image_service.validate_image_bytes(real_png(3, 3), filename="large.png")


def test_content_type_does_not_make_invalid_bytes_valid(client):
    operator = _operator(client)
    product = create_approved_product(client, operator)
    response = _upload(
        client,
        operator,
        product["id"],
        "forged.png",
        b"plain text with an image content type",
        "image/png",
    )
    assert response.status_code == 422


def test_valid_image_with_generic_content_type_is_accepted(client):
    operator = _operator(client)
    product = create_approved_product(client, operator)
    response = _upload(
        client,
        operator,
        product["id"],
        "valid.png",
        real_png(),
        "application/octet-stream",
    )
    assert response.status_code == 201, response.text
    assert response.json()["width"] == 2
    assert response.json()["height"] == 2


def test_provider_non_image_bytes_create_no_asset_or_partial_file(
    client, monkeypatch, db_session, tmp_path
):
    operator = _operator(client)
    product = create_approved_product(client, operator)
    reference = _upload(
        client,
        operator,
        product["id"],
        "reference.png",
        real_png(),
        "image/png",
    ).json()
    files_before = {path for path in tmp_path.rglob("*") if path.is_file()}
    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_service,
        "generate_image_with_provider",
        lambda **_kwargs: [b"provider-returned-text"],
    )

    response = client.post(
        IMAGE_TASKS_PATH,
        headers=operator,
        json={
            "product_id": product["id"],
            "style": "minimal",
            "reference_asset_id": reference["id"],
        },
    )
    assert response.status_code == 202
    task = client.get(
        f"{IMAGE_TASKS_PATH}/{response.json()['task_id']}", headers=operator
    ).json()
    assert task["status"] == "failed"
    assert (
        db_session.query(Asset)
        .filter(
            Asset.product_id == product["id"],
            Asset.asset_type == "generated",
        )
        .count()
        == 0
    )
    assert {path for path in tmp_path.rglob("*") if path.is_file()} == files_before
    assert not any(path.name.endswith(".part") for path in tmp_path.rglob("*"))


def test_generated_asset_uses_validated_dimensions_and_opaque_local_name(
    client, monkeypatch, db_session, tmp_path
):
    operator = _operator(client)
    product = create_approved_product(client, operator)
    reference = _upload(
        client,
        operator,
        product["id"],
        "reference.png",
        real_png(),
        "image/png",
    ).json()
    monkeypatch.setattr(image_service, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_service,
        "generate_image_with_provider",
        lambda **_kwargs: [real_png(5, 6)],
    )

    response = client.post(
        IMAGE_TASKS_PATH,
        headers=operator,
        json={
            "product_id": product["id"],
            "style": "minimal",
            "reference_asset_id": reference["id"],
        },
    )
    assert response.status_code == 202
    task = client.get(
        f"{IMAGE_TASKS_PATH}/{response.json()['task_id']}", headers=operator
    ).json()
    assert task["status"] == "completed"
    asset = (
        db_session.query(Asset)
        .filter(
            Asset.product_id == product["id"],
            Asset.asset_type == "generated",
        )
        .one()
    )
    assert (asset.width, asset.height) == (5, 6)
    assert asset.url.startswith("/uploads/")
    assert "http" not in asset.url
    assert os.path.isfile(tmp_path / asset.url.rsplit("/", 1)[-1])
