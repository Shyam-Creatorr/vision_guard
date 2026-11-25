from io import BytesIO
from pathlib import Path
import re
import uuid

from PIL import Image, ImageOps

from app.core.config import get_settings
from app.core.exceptions import AppError

ALLOWED_MAGIC: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def detect_mime_from_magic_bytes(raw: bytes) -> str | None:
    if len(raw) < 12:
        return None
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def sanitize_filename(filename: str | None) -> str:
    base = Path(filename or "diagram.png").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return cleaned[:120] or "diagram.png"


def save_validated_upload(raw_bytes: bytes, original_filename: str | None) -> tuple[str, str, str, int, int, str]:
    """
    Validates magic bytes, size, resolution, strips EXIF, and writes clean image.
    Returns (storage_key, mime_type, clean_filename, width_px, height_px, absolute_path).
    """
    settings = get_settings()
    if not raw_bytes:
        raise AppError("EMPTY_UPLOAD", "Uploaded file is empty.", status_code=400)
    if len(raw_bytes) > settings.max_upload_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"Diagram image exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB.",
            status_code=413,
        )

    mime_type = detect_mime_from_magic_bytes(raw_bytes)
    if mime_type not in ALLOWED_MAGIC:
        raise AppError(
            "UNSUPPORTED_MEDIA_TYPE",
            "Only valid JPG, PNG, or WEBP diagram images are supported (magic-byte check failed).",
            status_code=400,
        )

    try:
        Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_DIMENSION * settings.MAX_IMAGE_DIMENSION * 2
        with Image.open(BytesIO(raw_bytes)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            if width < 64 or height < 64:
                raise AppError(
                    "IMAGE_TOO_SMALL",
                    "Image dimensions are too small (minimum 64x64 pixels).",
                    status_code=400,
                )
            if width > settings.MAX_IMAGE_DIMENSION or height > settings.MAX_IMAGE_DIMENSION:
                img.thumbnail((settings.MAX_IMAGE_DIMENSION, settings.MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                width, height = img.size

            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            elif img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg

            upload_dir = settings.upload_path
            upload_dir.mkdir(parents=True, exist_ok=True)
            storage_key = f"{uuid.uuid4().hex}.png"
            dest = (upload_dir / storage_key).resolve()
            if upload_dir not in dest.parents:
                raise AppError("INVALID_STORAGE_PATH", "Invalid storage path.", status_code=500)

            # Save fresh PNG with zero EXIF/metadata
            img.save(dest, format="PNG", optimize=True)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "CORRUPT_IMAGE",
            "Uploaded file could not be decoded as a valid image.",
            status_code=400,
        ) from exc

    return storage_key, mime_type, sanitize_filename(original_filename), width, height, str(dest)


def resolve_upload_file(storage_key: str) -> Path:
    settings = get_settings()
    upload_dir = settings.upload_path
    safe_name = Path(storage_key).name
    target = (upload_dir / safe_name).resolve()
    if upload_dir not in target.parents or not target.exists():
        raise AppError("IMAGE_NOT_FOUND", "Requested diagram file was not found.", status_code=404)
    return target
