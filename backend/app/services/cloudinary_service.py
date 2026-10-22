"""Shared Cloudinary image storage for application-managed media."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import cloudinary
import cloudinary.uploader
import cloudinary.utils
import httpx
from fastapi import HTTPException

from app.core.config import settings


def _configure() -> None:
    values = (settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET)
    if not all(values):
        raise HTTPException(503, "Cloudinary image storage is not configured")
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=settings.CLOUDINARY_SECURE,
    )


def upload_image(blob: bytes, *, folder: str, private: bool = False, filename: str | None = None) -> dict[str, Any]:
    """Upload an image and return only persistence-safe delivery metadata."""
    _configure()
    options: dict[str, Any] = {
        "folder": folder.strip("/"),
        "resource_type": "image",
        "type": "authenticated" if private else "upload",
        "unique_filename": True,
        "overwrite": False,
        "secure": settings.CLOUDINARY_SECURE,
    }
    if filename:
        options["original_filename"] = filename
    try:
        result = cloudinary.uploader.upload(BytesIO(blob), **options)
    except Exception as exc:
        raise HTTPException(502, "Cloudinary image upload failed") from exc
    if not result.get("public_id") or not result.get("secure_url") or result.get("type", options["type"]) != options["type"]:
        delete_image(result.get("public_id"), private=result.get("type", options["type"]) == "authenticated")
        raise HTTPException(502, "Cloudinary returned incomplete or invalid image metadata")
    return {
        "public_id": result.get("public_id"),
        "secure_url": result.get("secure_url"),
        "width": result.get("width"),
        "height": result.get("height"),
        "format": result.get("format"),
        "bytes": result.get("bytes"),
        "resource_type": result.get("resource_type", "image"),
        "type": result.get("type", options["type"]),
    }


def delete_image(public_id: str | None, *, private: bool = False) -> None:
    if not public_id:
        return
    try:
        _configure()
        cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            type="authenticated" if private else "upload",
            invalidate=True,
        )
    except Exception:
        # Deletion is cleanup. The database mutation should not be rolled back
        # just because a stale remote asset could not be removed.
        return


def signed_private_url(public_id: str) -> str:
    _configure()
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        secure=settings.CLOUDINARY_SECURE,
        resource_type="image",
        type="authenticated",
        sign_url=True,
    )
    return url


def fetch_private_image(public_id: str) -> tuple[bytes, str]:
    """Fetch an authenticated Cloudinary image for an authorized API caller."""
    url = signed_private_url(public_id)
    try:
        response = httpx.get(url, timeout=20.0)
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(502, "Private image delivery is temporarily unavailable") from exc
    return response.content, response.headers.get("content-type", "image/jpeg")
