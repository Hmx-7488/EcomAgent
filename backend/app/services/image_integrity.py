"""Trusted image decoding, bounded HTTPS download and atomic local storage."""

from __future__ import annotations

import io
import ipaddress
import os
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, UnidentifiedImageError


SUPPORTED_IMAGE_FORMATS = {
    "PNG": {".png"},
    "JPEG": {".jpg", ".jpeg"},
    "WEBP": {".webp"},
    "BMP": {".bmp"},
}
ALLOWED_EXTENSIONS = {
    extension
    for extensions in SUPPORTED_IMAGE_FORMATS.values()
    for extension in extensions
}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_IMAGE_WIDTH = 10_000
MAX_IMAGE_HEIGHT = 10_000
MAX_IMAGE_PIXELS = 25_000_000
MAX_DOWNLOAD_REDIRECTS = 2
DOWNLOAD_TIMEOUT = httpx.Timeout(20.0, connect=5.0, read=15.0)


@dataclass(frozen=True)
class ValidatedImage:
    """Trusted image facts obtained from a complete Pillow decode."""

    format: str
    extension: str
    width: int
    height: int
    size_bytes: int


def validate_image_bytes(
    file_bytes: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    max_file_size: int = MAX_FILE_SIZE,
    max_image_width: int = MAX_IMAGE_WIDTH,
    max_image_height: int = MAX_IMAGE_HEIGHT,
    max_image_pixels: int = MAX_IMAGE_PIXELS,
) -> ValidatedImage:
    """Decode, verify and reload bytes; never trust transport Content-Type."""

    del content_type
    if not file_bytes:
        raise ValueError("Image file is empty")
    if len(file_bytes) > max_file_size:
        raise ValueError(
            f"File too large: {len(file_bytes)} bytes. Maximum: {max_file_size} bytes"
        )

    supplied_extension = Path(filename or "").suffix.lower()
    if filename and supplied_extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {supplied_extension or '<none>'}. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(file_bytes)) as image:
                detected_format = (image.format or "").upper()
                width, height = image.size
                image.verify()
            with Image.open(io.BytesIO(file_bytes)) as image:
                reloaded_format = (image.format or "").upper()
                image.load()
                reloaded_size = image.size
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ValueError("Image bytes could not be decoded and verified") from exc

    if detected_format not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError(f"Unsupported decoded image format: {detected_format or 'unknown'}")
    if reloaded_format != detected_format or reloaded_size != (width, height):
        raise ValueError("Image metadata changed during full decode")
    if width <= 0 or height <= 0:
        raise ValueError("Image width and height must be positive")
    if width > max_image_width or height > max_image_height:
        raise ValueError(
            f"Image dimensions exceed {max_image_width}x{max_image_height}"
        )
    if width * height > max_image_pixels:
        raise ValueError(
            f"Image pixel count exceeds maximum of {max_image_pixels}"
        )

    allowed_for_format = SUPPORTED_IMAGE_FORMATS[detected_format]
    if supplied_extension and supplied_extension not in allowed_for_format:
        raise ValueError(
            f"File extension {supplied_extension} does not match decoded "
            f"{detected_format} image"
        )
    canonical_extension = ".jpg" if detected_format == "JPEG" else sorted(allowed_for_format)[0]
    return ValidatedImage(
        format=detected_format,
        extension=canonical_extension,
        width=width,
        height=height,
        size_bytes=len(file_bytes),
    )


def write_atomic_image(
    upload_dir: str,
    file_bytes: bytes,
    image: ValidatedImage,
) -> tuple[str, str]:
    """Persist already validated bytes under an opaque local name."""

    os.makedirs(upload_dir, exist_ok=True)
    opaque_name = f"{uuid.uuid4().hex}{image.extension}"
    final_path = os.path.join(upload_dir, opaque_name)
    temporary_path = f"{final_path}.{uuid.uuid4().hex}.part"
    try:
        with open(temporary_path, "xb") as output_file:
            output_file.write(file_bytes)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary_path, final_path)
    except Exception:
        remove_files((temporary_path, final_path))
        raise
    return opaque_name, final_path


def remove_files(paths) -> None:
    """Best-effort cleanup for files that must not outlive a failed transaction."""

    for path in paths:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _validated_https_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Provider image URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("Provider image URL cannot include credentials")
    hostname = parsed.hostname.lower()
    if hostname == "localhost":
        raise ValueError("Provider image URL cannot target localhost")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("Provider image URL cannot target a private address")
    return url


def download_https_image(url: str) -> bytes:
    """Download a temporary Provider URL with bounded redirects and body size."""

    current_url = _validated_https_url(url)
    try:
        with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=False) as client:
            for redirect_count in range(MAX_DOWNLOAD_REDIRECTS + 1):
                with client.stream(
                    "GET",
                    current_url,
                    headers={"Accept": "image/*"},
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count >= MAX_DOWNLOAD_REDIRECTS:
                            raise ValueError("Provider image redirect limit exceeded")
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Provider image redirect omitted Location")
                        current_url = _validated_https_url(
                            urljoin(current_url, location)
                        )
                        continue

                    response.raise_for_status()
                    declared_size = response.headers.get("content-length")
                    if declared_size:
                        try:
                            if int(declared_size) > MAX_FILE_SIZE:
                                raise ValueError("Provider image response is too large")
                        except ValueError as exc:
                            if "too large" in str(exc):
                                raise
                            raise ValueError(
                                "Provider image Content-Length is invalid"
                            ) from exc

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_FILE_SIZE:
                            raise ValueError("Provider image response is too large")

                    path_name = Path(urlparse(current_url).path).name
                    extension = Path(path_name).suffix.lower()
                    validation_name = (
                        path_name if extension in ALLOWED_EXTENSIONS else None
                    )
                    payload = bytes(body)
                    validate_image_bytes(
                        payload,
                        filename=validation_name,
                        content_type=response.headers.get("content-type"),
                    )
                    return payload
    except httpx.TimeoutException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Provider image download failed validation") from exc

    raise RuntimeError("Provider image download failed")
