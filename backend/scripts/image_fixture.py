"""Offline-only image helpers for acceptance scripts and tests."""

from __future__ import annotations

import io

from PIL import Image


def png_bytes(
    width: int = 8,
    height: int = 8,
    *,
    color: tuple[int, int, int] = (35, 112, 76),
) -> bytes:
    """Return a small, genuinely decodable PNG generated entirely in memory."""

    output = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(output, format="PNG")
    return output.getvalue()


def verify_and_load_png(payload: bytes) -> tuple[int, int]:
    """Run Pillow verify and a separate full load, returning image dimensions."""

    with Image.open(io.BytesIO(payload)) as image:
        assert image.format == "PNG"
        size = image.size
        image.verify()
    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        assert image.size == size
    return size
