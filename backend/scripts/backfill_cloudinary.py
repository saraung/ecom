"""Backfill legacy local content and return evidence into Cloudinary.

The command is intentionally dry-run by default. Use ``--apply`` only after
reviewing the candidate list. It never deletes local files, so the operation
can be retried or rolled back at the database/URL level without data loss.

Product image URL records are not changed: they may point to external URLs,
and there is no reliable local source to upload for those records.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlmodel import Session, select

import app.models  # noqa: F401 — register all models and relationships
from app.db.database import engine
from app.models.content_block import ContentBlock
from app.models.product_return import ReturnEvidence
from app.services.cloudinary_service import delete_image, upload_image
from app.services.return_evidence import evidence_path


ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = ROOT / "uploads" / "content"


def local_content_file(image_url: str | None) -> Path | None:
    if not image_url:
        return None
    path = unquote(urlparse(image_url).path)
    prefix = "/uploads/content/"
    if not path.startswith(prefix):
        return None
    filename = path[len(prefix):]
    if not filename or Path(filename).name != filename:
        return None
    candidate = (CONTENT_ROOT / filename).resolve()
    if candidate.parent != CONTENT_ROOT.resolve() or not candidate.is_file():
        return None
    return candidate


def candidates(session: Session) -> list[tuple[str, object, Path]]:
    result: list[tuple[str, object, Path]] = []
    for block in session.exec(select(ContentBlock).where(
        ContentBlock.image_public_id.is_(None), ContentBlock.image_url.is_not(None)
    )):
        path = local_content_file(block.image_url)
        if path:
            result.append(("banner", block, path))
        elif "/uploads/content/" in (block.image_url or ""):
            print(f"SKIP banner {block.id}: local source is missing or invalid")
    for evidence in session.exec(select(ReturnEvidence).where(ReturnEvidence.cloudinary_public_id.is_(None))):
        try:
            path = evidence_path(evidence.storage_key)
        except Exception as exc:
            print(f"SKIP return evidence {evidence.id}: {exc}")
            continue
        if path.is_file():
            result.append(("return", evidence, path))
        else:
            print(f"SKIP return evidence {evidence.id}: local source is missing")
    return result


def backfill(apply: bool) -> int:
    with Session(engine) as session:
        rows = candidates(session)
        if not rows:
            print("No legacy local image records found.")
            return 0
        print(f"Found {len(rows)} legacy local image(s).")
        for kind, row, path in rows:
            print(f"{'UPLOAD' if apply else 'DRY-RUN'} {kind}: {path}")
            if not apply:
                continue
            asset = upload_image(
                path.read_bytes(),
                folder="com/banners" if kind == "banner" else f"com/returns/{row.return_id}",
                private=kind == "return",
                filename=path.name,
            )
            try:
                if not asset.get("public_id") or not asset.get("secure_url"):
                    raise RuntimeError(f"Cloudinary returned incomplete metadata for {path}")
                if kind == "banner":
                    row.image_url = asset["secure_url"]
                    row.image_public_id = asset["public_id"]
                else:
                    row.secure_url = asset["secure_url"]
                    row.cloudinary_public_id = asset["public_id"]
                    row.cloudinary_type = asset.get("type")
                session.add(row)
                session.commit()
            except Exception:
                session.rollback()
                delete_image(asset.get("public_id"), private=kind == "return")
                raise
        return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Upload files and persist Cloudinary metadata")
    args = parser.parse_args()
    engine.echo = False
    backfill(args.apply)
