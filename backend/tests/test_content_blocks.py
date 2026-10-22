"""
Tests for storefront content blocks (Phase E).

Covers:
  1. Public read returns active in-window blocks keyed by slot.
  2. Drafts, disabled, expired, and future blocks are excluded.
  3. Key filtering works; unknown keys return nothing (no error).
  4. Admin list sees everything regardless of window/state.

Run:  PYTHONPATH=. .venv/bin/python -m pytest tests/test_content_blocks.py -q
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import SQLModel, Session, create_engine

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.content_block import ContentBlock
from app.repositories import content as content_repo


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _block(s, key, **kw):
    defaults = dict(title=f"Title {key}", body="Body", is_active=True)
    defaults.update(kw)
    b = ContentBlock(key=key, **defaults)
    s.add(b)
    s.commit()
    s.refresh(b)
    return b


@pytest.fixture()
def seeded(session):
    now = datetime.now(timezone.utc)
    _block(session, "announcement.bar", title="Sale live!")
    _block(session, "home.hero", title="Hero")
    _block(session, "draft.promo", is_active=False)
    _block(
        session, "expired.promo",
        starts_at=now - timedelta(days=10), ends_at=now - timedelta(days=1),
    )
    _block(
        session, "future.promo",
        starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=8),
    )
    _block(
        session, "windowed.promo",
        starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1),
    )
    return session


def test_1_live_blocks_only(seeded):
    live = content_repo.get_live_blocks(seeded)
    assert set(live) == {"announcement.bar", "home.hero", "windowed.promo"}, set(live)
    assert [b.title for b in live["announcement.bar"]] == ["Sale live!"]


def test_2_key_filter_and_unknown_keys(seeded):
    assert set(content_repo.get_live_blocks(seeded, keys=["home.hero"])) == {"home.hero"}
    assert content_repo.get_live_blocks(seeded, keys=["nope"]) == {}


def test_3_admin_list_sees_everything(seeded):
    rows, total = content_repo.list_blocks_admin(seeded)
    assert total == 6
    assert len(rows) == 6
    assert content_repo.get_block_by_key(seeded, "draft.promo") is not None


def test_4_slot_orders_by_sort_order(seeded):
    from app.models.content_block import ContentBlock as CB

    second = CB(key="announcement.bar", title="Second", sort_order=0)
    first = CB(key="announcement.bar", title="First", sort_order=-1)
    seeded.add(second)
    seeded.add(first)
    seeded.commit()
    live = content_repo.get_live_blocks(seeded, keys=["announcement.bar"])
    titles = [b.title for b in live["announcement.bar"]]
    # sort_order -1 first, then the two sort_order=0 rows oldest-first.
    assert titles == ["First", "Sale live!", "Second"], titles


def _upload_file(filename, blob, content_type="image/png"):
    import io as _io
    from fastapi import UploadFile

    return UploadFile(filename=filename, file=_io.BytesIO(blob), headers={"content-type": content_type})


def _png(width, height, size_pad=0):
    import io as _io
    from PIL import Image as _Image

    buf = _io.BytesIO()
    _Image.new("RGB", (width, height), "red").save(buf, format="PNG")
    blob = buf.getvalue() + (b"\x00" * size_pad)
    return blob


def _request():
    import types

    return types.SimpleNamespace(base_url="http://testserver/")


def test_5_upload_accepts_and_warns_on_aspect(seeded, monkeypatch):
    import asyncio as _asyncio

    from fastapi import HTTPException
    from app.api.v1.admin import content as admin_content
    monkeypatch.setattr(admin_content, "upload_image", lambda blob, folder, filename: {
        "secure_url": "https://res.cloudinary.com/test/image/upload/banner.jpg",
        "public_id": f"{folder}/banner",
        "bytes": len(blob),
    })

    def _call(slot, upload):
        return _asyncio.new_event_loop().run_until_complete(
            admin_content.upload_content_image(_request(), slot, upload, None)
        )

    # 800x80 PNG for the strip: correct 10:1, no warning.
    res = _call("announcement.bar", _upload_file("strip.png", _png(800, 80)))
    assert res.url.startswith("https://res.cloudinary.com/test/")
    assert (res.width, res.height) == (800, 80)
    assert res.aspect_warning is None

    # Square image into the 10:1 slot: succeeds with a warning.
    res2 = _call("announcement.bar", _upload_file("sq.png", _png(100, 100)))
    assert res2.aspect_warning is not None and "800" in res2.aspect_warning

    # Oversize for the strip (>1 MB): hard 413.
    with __import__("pytest").raises(HTTPException) as exc:
        _call(
            "announcement.bar",
            _upload_file("big.png", _png(800, 80, size_pad=2_000_000)),
        )
    assert exc.value.status_code == 413

    # Non-image extension: 415.
    with __import__("pytest").raises(HTTPException) as exc2:
        _call(
            "home.hero",
            _upload_file("evil.txt", b"not an image", "text/plain"),
        )
    assert exc2.value.status_code == 415

    # Oversized dimensions are downscaled to display size (aspect kept).
    res3 = _call("home.hero", _upload_file("huge.png", _png(2500, 1000)))
    assert res3.width == 1920, (res3.width, res3.height)
    assert abs(res3.width / res3.height - 2.5) < 0.01
