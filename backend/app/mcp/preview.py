"""Generic signed preview tokens for MCP write tools (no storage).

Mirrors the order-tool pattern (signed + expiring + bound), generalized:
the token binds the authenticated user, the target, and the EXACT proposed
changes as canonical JSON. Execution compares the live database state and
the resubmitted changes against the token — any drift fails closed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from app.core.config import settings

WRITE_PREVIEW_TTL_MINUTES = 10
WRITE_PREVIEW_TYPE = "mcp_write_preview"


def _canonical_changes(changes: dict) -> str:
    return json.dumps(changes, sort_keys=True, separators=(",", ":"), default=str)


def issue_write_preview(
    user_id: UUID, kind: str, target_id: str, changes: dict, fingerprint: dict,
    *, ttl_minutes: int = WRITE_PREVIEW_TTL_MINUTES,
) -> str:
    """Sign a preview: who, target, exact changes, live-state fingerprint, expiry."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    canonical = _canonical_changes(changes)
    fp_canonical = _canonical_changes(fingerprint)
    return jwt.encode(
        {
            "sub": str(user_id),
            "kind": kind,
            "tid": str(target_id),
            "chg": canonical,
            "chash": hashlib.sha256(canonical.encode()).hexdigest(),
            "fp": fp_canonical,
            "exp": expire,
            "type": WRITE_PREVIEW_TYPE,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def verify_write_preview(
    preview_token: str | None, user_id: UUID, kind: str, target_id: str,
    changes: dict, fingerprint: dict,
) -> dict[str, Any] | str:
    """Return the decoded payload, or an error string (never raises).

    Checks signature/expiry/type, then exact binding: same user, same
    tool kind, same target, byte-identical proposed changes, and an
    unchanged live-state fingerprint (concurrent modification fails closed).
    """
    if not preview_token or not str(preview_token).strip():
        return "A fresh preview_token is required to execute this change"
    try:
        preview = jwt.decode(
            str(preview_token).strip(),
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return "Invalid or expired preview_token; request a new preview"
    if preview.get("type") != WRITE_PREVIEW_TYPE:
        return "Invalid preview_token; request a new preview"
    if preview.get("sub") != str(user_id) or preview.get("kind") != kind:
        return "Preview does not match this user or action; request a new preview"
    if preview.get("tid") != str(target_id):
        return "Preview does not match this target; request a new preview"
    canonical = _canonical_changes(changes)
    if (
        preview.get("chg") != canonical
        or preview.get("chash") != hashlib.sha256(canonical.encode()).hexdigest()
    ):
        return "Preview is stale (proposed changes differ); request a new preview"
    if preview.get("fp") != _canonical_changes(fingerprint):
        return "Preview is stale (record changed since preview); request a new preview"
    return preview
