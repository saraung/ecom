"""Cloudinary media contracts through real HTTP, auth, and DB boundaries."""
import io
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import event, text
from sqlmodel import Session, select

from app.api.v1 import product_images, reviews
from app.api.v1.admin import content, reviews as admin_reviews
from app.core.config import settings
from app.models.admin_audit import AdminAuditLog
from app.models.content_block import ContentBlock
from app.models.product import ProductVariant
from app.models.product_image import ProductImage
from app.models.review import Review
from app.models.review_image import ReviewImage
from app.services import cloudinary_service as storage, product_return
from tests.test_product_returns import env, create, photo  # noqa: F401


@pytest.fixture
def media(env, monkeypatch):
    for router in (product_images.router, reviews.router, content.router, admin_reviews.router):
        env.client.app.include_router(router, prefix="/api/v1")
    with env.engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
    with Session(env.engine) as session:
        env.product_id = session.get(ProductVariant, env.ids["variant1"]).product_id
    for key, value in {"CLOUDINARY_CLOUD_NAME": "test-cloud", "CLOUDINARY_API_KEY": "test-key",
                       "CLOUDINARY_API_SECRET": "test-secret", "CLOUDINARY_SECURE": True}.items():
        monkeypatch.setattr(settings, key, value)
    env.uploads, env.destroyed = [], []
    def upload(file, **options):
        blob = file.read()
        asset = {
            "public_id": f"{options['folder']}/{uuid4().hex}",
            "secure_url": f"https://res.cloudinary.com/test-cloud/image/{options['type']}/{uuid4().hex}.jpg",
            "type": options["type"], "bytes": len(blob), "width": 12, "height": 12,
        }
        env.uploads.append({"blob": blob, "options": options, "asset": asset})
        return asset
    def destroy(public_id, **options):
        env.destroyed.append((public_id, options))
        return {"result": "ok"}
    monkeypatch.setattr(storage.cloudinary.uploader, "upload", upload)
    monkeypatch.setattr(storage.cloudinary.uploader, "destroy", destroy)
    monkeypatch.setattr(product_return, "upload_image", storage.upload_image)
    return env


def product_upload(media, actor="admin", **extra):
    return media.client.post(f"/api/v1/products/{media.product_id}/images/upload",
                             headers=media.headers[actor], files=[("file", photo()[1])],
                             data={"alt_text": "  Front view  "}, **extra)


def review_upload(media, actor="buyer", count=2):
    return media.client.post(f"/api/v1/reviews/{media.product_id}/with-images",
                             headers=media.headers[actor], data={"data": json.dumps({"rating": 5, "comment": "Great"})},
                             files=[photo()] * count)


def test_product_upload_metadata_alt_text_order_and_url_compatibility(media):
    base = f"/api/v1/products/{media.product_id}/images"
    legacy = media.client.post(base, headers=media.headers["admin"], json={"url": "https://example.test/old.jpg"})
    assert legacy.status_code == 201 and legacy.json()["cloudinary_public_id"] is None
    result = product_upload(media)
    assert result.status_code == 201, result.text
    row = result.json()
    assert row["url"] == row["secure_url"] and row["sort_order"] == 1 and row["alt_text"] == "Front view"
    assert row["cloudinary_public_id"].startswith(f"com/products/{media.product_id}/")
    assert media.uploads[0]["options"]["type"] == "upload"
    assert len(media.client.get(base).json()) == 2
    with Session(media.engine) as session:
        assert session.get(ProductImage, UUID(row["id"])).secure_url == row["secure_url"]
    assert media.client.delete(f"{base}/{row['id']}", headers=media.headers["admin"]).status_code == 204
    assert media.destroyed[0][0] == row["cloudinary_public_id"]


def test_product_url_replacement_clears_and_cleans_cloudinary_metadata(media):
    row = product_upload(media).json()
    url = f"/api/v1/products/{media.product_id}/images/{row['id']}"
    renamed = media.client.put(url, headers=media.headers["admin"], json={"alt_text": "Side"})
    assert renamed.json()["cloudinary_public_id"] == row["cloudinary_public_id"] and not media.destroyed
    replaced = media.client.put(url, headers=media.headers["admin"], json={"url": "https://example.test/new.jpg"})
    assert replaced.status_code == 200 and replaced.json()["secure_url"] is None
    assert replaced.json()["cloudinary_public_id"] is None
    assert media.destroyed[0][0] == row["cloudinary_public_id"]


@pytest.mark.parametrize("actor", ["buyer"])
def test_product_upload_requires_image_permission(media, actor):
    assert product_upload(media, actor).status_code == 403
    assert not media.uploads


def test_product_upload_rejects_invalid_or_oversized_files_before_storage(media):
    url = f"/api/v1/products/{media.product_id}/images/upload"
    for blob, mime, expected in ((b"invalid", "image/png", 415), (b"<svg/>", "image/svg+xml", 415),
                                  (b"x" * (10 * 1024 * 1024 + 1), "image/png", 413)):
        response = media.client.post(url, headers=media.headers["admin"], files={"file": ("file.png", blob, mime)})
        assert response.status_code == expected
    assert not media.uploads


def test_product_failed_commit_cleans_uploaded_asset(media):
    def fail(session):
        raise RuntimeError("commit failed")
    event.listen(Session, "before_commit", fail)
    try:
        assert product_upload(media).status_code == 500
    finally:
        event.remove(Session, "before_commit", fail)
    with Session(media.engine) as session:
        assert session.exec(select(ProductImage)).all() == []
    assert media.destroyed[0][0] == media.uploads[0]["asset"]["public_id"]


def test_review_images_survive_public_owner_admin_and_update_reads(media):
    response = review_upload(media)
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["is_verified_purchase"] and len(row["images"]) == 2
    assert [image["sort_order"] for image in row["images"]] == [0, 1]
    assert all(upload["options"]["folder"] == f"com/reviews/{row['id']}" for upload in media.uploads)
    for path, headers in ((f"/api/v1/reviews/products/{media.product_id}", {}),
                          ("/api/v1/reviews/my-reviews", media.headers["buyer"]),
                          ("/api/v1/admin/reviews", media.headers["admin"])):
        result = media.client.get(path, headers=headers)
        assert result.status_code == 200, result.text
        rows = result.json()["items"] if "admin" in path else result.json()
        assert len(rows[0]["images"]) == 2
    updated = media.client.put(f"/api/v1/reviews/{row['id']}", headers=media.headers["buyer"], json={"rating": 4})
    assert updated.status_code == 200 and len(updated.json()["images"]) == 2
    hidden = media.client.put(f"/api/v1/admin/reviews/{row['id']}/visibility", headers=media.headers["admin"], json={"is_hidden": True})
    assert hidden.status_code == 200 and len(hidden.json()["images"]) == 2
    assert media.client.get(f"/api/v1/reviews/products/{media.product_id}").json() == []


@pytest.mark.parametrize("actor,path", [("buyer", "/api/v1/reviews"), ("admin", "/api/v1/admin/reviews")])
def test_review_deletion_removes_image_rows_and_remote_assets(media, actor, path):
    row = review_upload(media).json()
    if actor == "admin":
        from fastapi.testclient import TestClient
        with TestClient(media.client.app) as client:
            response = client.delete(f"{path}/{row['id']}", headers=media.headers[actor])
    else:
        response = media.client.delete(f"{path}/{row['id']}", headers=media.headers[actor])
    assert response.status_code == 204, response.text
    with Session(media.engine) as session:
        assert session.exec(select(ReviewImage)).all() == [] and session.exec(select(Review)).all() == []
        if actor == "admin":
            assert session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "review.deleted")).first()
    assert {item[0] for item in media.destroyed} == {item["asset"]["public_id"] for item in media.uploads}


def test_review_upload_requires_verified_purchase_and_rejects_duplicates(media):
    assert review_upload(media, "other").status_code == 403 and not media.uploads
    assert review_upload(media).status_code == 200
    assert review_upload(media).status_code == 400 and len(media.uploads) == 2


def test_review_partial_upload_failure_rolls_back_review_and_all_images(media, monkeypatch):
    original = storage.cloudinary.uploader.upload
    def fail_second(file, **options):
        if media.uploads:
            raise RuntimeError("provider unavailable")
        return original(file, **options)
    monkeypatch.setattr(storage.cloudinary.uploader, "upload", fail_second)
    assert review_upload(media).status_code == 502
    with Session(media.engine) as session:
        assert session.exec(select(ReviewImage)).all() == [] and session.exec(select(Review)).all() == []
    assert media.destroyed[0][0] == media.uploads[0]["asset"]["public_id"]
    monkeypatch.setattr(storage.cloudinary.uploader, "upload", original)
    assert review_upload(media).status_code == 200  # failed attempt did not consume the review slot


def test_review_commit_failure_does_not_publish_review_or_images(media):
    def fail(session):
        raise RuntimeError("commit failed")
    event.listen(Session, "before_commit", fail)
    try:
        assert review_upload(media).status_code == 502
    finally:
        event.remove(Session, "before_commit", fail)
    with Session(media.engine) as session:
        assert session.exec(select(ReviewImage)).all() == [] and session.exec(select(Review)).all() == []
    assert len(media.destroyed) == 2


def test_review_rejects_invalid_images_and_count_before_publishing(media):
    assert review_upload(media, count=7).status_code == 422
    response = media.client.post(f"/api/v1/reviews/{media.product_id}/with-images", headers=media.headers["buyer"],
                                 data={"data": '{"rating":5}'}, files=[photo(b"not an image")])
    assert response.status_code == 415 and not media.uploads
    with Session(media.engine) as session:
        assert session.exec(select(Review)).all() == []


def test_cms_upload_metadata_replacement_and_shared_asset_cleanup(media):
    upload = media.client.post("/api/v1/admin/content/images?slot=home.hero", headers=media.headers["admin"],
                               files=[("file", photo()[1])])
    assert upload.status_code == 200, upload.text
    asset = upload.json()
    assert asset["public_id"].startswith("com/banners/")
    blocks = []
    for title in ("First", "Second"):
        result = media.client.post("/api/v1/admin/content/blocks", headers=media.headers["admin"],
                                   json={"key": "home.hero", "title": title, "image_url": asset["url"], "image_public_id": asset["public_id"]})
        assert result.status_code == 201, result.text
        blocks.append(result.json()["id"])
    replaced = media.client.put(f"/api/v1/admin/content/blocks/{blocks[0]}", headers=media.headers["admin"],
                                json={"image_url": "https://example.test/external.jpg"})
    assert replaced.status_code == 200 and replaced.json()["image_public_id"] is None
    assert not media.destroyed  # second block still uses the same asset
    assert media.client.delete(f"/api/v1/admin/content/blocks/{blocks[1]}", headers=media.headers["admin"]).status_code == 204
    assert media.destroyed[0][0] == asset["public_id"]
    with Session(media.engine) as session:
        assert len(session.exec(select(ContentBlock)).all()) == 1


def test_returns_use_authenticated_cloudinary_uploads(media):
    row = create(media, images=[photo()])
    upload = media.uploads[0]
    assert upload["options"]["folder"] == f"com/returns/{row['id']}"
    assert upload["options"]["type"] == "authenticated"
    with Image.open(io.BytesIO(upload["blob"])) as image:
        assert image.format == "JPEG"


def test_service_signed_private_delivery_and_errors(media, monkeypatch):
    public_id = "com/returns/request/image"
    url = storage.signed_private_url(public_id)
    assert url.startswith("https://res.cloudinary.com/test-cloud/image/authenticated/s--") and public_id in url
    requests = []
    def fetch(url, **options):
        requests.append((url, options))
        return SimpleNamespace(content=b"image", headers={"content-type": "image/jpeg"}, raise_for_status=lambda: None)
    monkeypatch.setattr(storage.httpx, "get", fetch)
    assert storage.fetch_private_image(public_id) == (b"image", "image/jpeg")
    assert requests == [(url, {"timeout": 20.0})]
    def unavailable(*args, **kwargs):
        raise RuntimeError("provider secret error")
    monkeypatch.setattr(storage.httpx, "get", unavailable)
    with pytest.raises(HTTPException) as error:
        storage.fetch_private_image(public_id)
    assert error.value.status_code == 502 and "secret" not in error.value.detail


def test_service_rejects_wrong_private_delivery_type_and_cleans_asset(media, monkeypatch):
    monkeypatch.setattr(storage.cloudinary.uploader, "upload", lambda *args, **kwargs: {
        "public_id": "com/returns/request/image", "secure_url": "https://example.test/image.jpg", "type": "upload",
    })
    with pytest.raises(HTTPException) as error:
        storage.upload_image(b"image", folder="com/returns/request", private=True)
    assert error.value.status_code == 502
    assert media.destroyed == [("com/returns/request/image", {"resource_type": "image", "type": "upload", "invalidate": True})]


def test_missing_cloudinary_credentials_are_reported_on_upload_but_cleanup_is_best_effort(media, monkeypatch):
    monkeypatch.setattr(settings, "CLOUDINARY_API_SECRET", None)
    assert product_upload(media).status_code == 503 and not media.uploads
    storage.delete_image("com/products/product/image")
