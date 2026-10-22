"""Bounded, sanitized private return images, never served by /uploads."""
import hashlib
import io
from pathlib import Path
import warnings

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PIXELS = 20_000_000


def storage_dir():
    path = Path(settings.RETURN_STORAGE_DIR)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if path == (ROOT / "uploads").resolve() or (ROOT / "uploads").resolve() in path.parents:
        raise HTTPException(503, "Return evidence storage must be private")
    return path


def evidence_path(key):
    directory = storage_dir()
    path = (directory / key).resolve()
    if path.parent != directory:
        raise HTTPException(404, "Evidence not found")
    return path


async def decode_images(files: list[UploadFile]):
    if len(files) > settings.RETURN_MAX_IMAGES:
        raise HTTPException(422, f"At most {settings.RETURN_MAX_IMAGES} images are allowed")
    images = []
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED or file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(415, "Evidence must be a JPEG, PNG or WebP image")
        chunks, size = [], 0
        while chunk := await file.read(256 * 1024):
            size += len(chunk)
            if size > settings.RETURN_IMAGE_MAX_BYTES:
                raise HTTPException(413, "Return image exceeds the configured size limit")
            chunks.append(chunk)
        blob = b"".join(chunks)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(blob)) as img:
                    if img.format not in {"JPEG", "PNG", "WEBP"} or img.width * img.height > MAX_PIXELS:
                        raise ValueError("Unsupported image or excessive dimensions")
                    img.verify()
                with Image.open(io.BytesIO(blob)) as img:
                    clean = ImageOps.exif_transpose(img).convert("RGB")
                    clean.thumbnail((2000, 2000))
                    out = io.BytesIO()
                    # Always re-encode: discard EXIF, comments and trailing executable bytes.
                    clean.save(out, format="JPEG", quality=85, optimize=True)
                    encoded = out.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(415, "Evidence is not a safe, readable image")
        if len(encoded) > settings.RETURN_IMAGE_MAX_BYTES:
            raise HTTPException(413, "Sanitized return image exceeds the size limit")
        images.append({"blob": encoded, "hash": hashlib.sha256(blob).hexdigest(),
                       "filename": "return-image.jpg"})
    return images
