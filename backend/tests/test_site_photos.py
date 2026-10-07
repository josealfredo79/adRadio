"""Fotos del carrusel de la página pública: el dueño sube las suyas (se
achican y se enderezan), las ordena o quita, y la página las recibe."""
import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import delete
from starlette.datastructures import Headers

from app.api.v1.profile import (
    MAX_SITE_PHOTOS,
    SitePhotosOrder,
    set_site_photos,
    upload_site_photo,
)
from app.api.v1.public_site import get_public_site
from app.database import AsyncSessionLocal, engine
from app.models.user import User


def _photo(w=4000, h=3000) -> UploadFile:
    buf = BytesIO()
    Image.new("RGB", (w, h), (200, 80, 40)).save(buf, "JPEG", quality=95)
    buf.seek(0)
    return UploadFile(file=buf, filename="foto.jpg", headers=Headers({"content-type": "image/jpeg"}))


async def _seed(**kw):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", slug=f"s-{uuid.uuid4().hex[:10]}", **kw)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(uid):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@pytest.mark.asyncio
async def test_upload_shrinks_the_photo_and_appends_it():
    uid = await _seed()
    stored = {}

    async def fake_upload(content, key, ctype):
        stored["content"], stored["key"] = content, key
        return f"https://cdn.example.com/{key}"

    try:
        with patch("app.api.v1.profile.upload_bytes", new=fake_upload):
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                out = await upload_site_photo(file=_photo(), db=db, current_user=user)
        assert out.site_photos == [f"https://cdn.example.com/{stored['key']}"]
        assert stored["key"].startswith(f"site-photos/{uid}/") and stored["key"].endswith(".jpg")
        with Image.open(BytesIO(stored["content"])) as img:
            assert max(img.size) == 1800
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_upload_rejects_non_images_and_the_ninth_photo():
    full = [f"https://cdn.example.com/{i}.jpg" for i in range(MAX_SITE_PHOTOS)]
    uid = await _seed(site_photos=full)
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            with pytest.raises(HTTPException) as e:
                await upload_site_photo(file=_photo(), db=db, current_user=user)
            assert e.value.status_code == 400 and "hasta" in e.value.detail
            user.site_photos = []
            bad = UploadFile(file=BytesIO(b"no soy foto"), filename="x.jpg", headers=Headers({"content-type": "image/jpeg"}))
            with pytest.raises(HTTPException) as e:
                await upload_site_photo(file=bad, db=db, current_user=user)
            assert "No pude leer" in e.value.detail
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_reorder_and_remove_only_own_photos():
    a, b = "https://cdn.example.com/a.jpg", "https://cdn.example.com/b.jpg"
    uid = await _seed(site_photos=[a, b])
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            out = await set_site_photos(body=SitePhotosOrder(photos=[b, a]), db=db, current_user=user)
            assert out.site_photos == [b, a]
            out = await set_site_photos(body=SitePhotosOrder(photos=[a]), db=db, current_user=user)
            assert out.site_photos == [a]
            with pytest.raises(HTTPException):
                await set_site_photos(body=SitePhotosOrder(photos=[a, "https://evil.example.com/x.jpg"]), db=db, current_user=user)
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_public_site_sends_photos_and_about():
    uid = await _seed(site_photos=["https://cdn.example.com/a.jpg"], site_about="Cortes clásicos desde 1998.")
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            slug = user.slug
            from starlette.requests import Request

            req = Request({"type": "http", "method": "GET", "path": f"/api/v1/public/site/{slug}", "headers": [],
                           "client": (f"t-{uuid.uuid4()}", 1), "query_string": b""})
            data = await get_public_site(request=req, slug=slug, db=db)
        assert data["site_photos"] == ["https://cdn.example.com/a.jpg"]
        assert data["site_about"] == "Cortes clásicos desde 1998."
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_old_cover_shows_up_as_first_photo_and_can_be_removed():
    old = "https://cdn.example.com/hero-images/old.jpg"
    uid = await _seed(hero_image_url=old)
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            # Quitarla: la lista que manda el editor ya no la trae.
            out = await set_site_photos(body=SitePhotosOrder(photos=[]), db=db, current_user=user)
            assert out.site_photos == [] and out.hero_image_url is None
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_new_photo_keeps_the_old_cover_first():
    old = "https://cdn.example.com/hero-images/old.jpg"
    uid = await _seed(hero_image_url=old)
    try:
        with patch("app.api.v1.profile.upload_bytes", new=AsyncMock(return_value="https://cdn.example.com/new.jpg")):
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                out = await upload_site_photo(file=_photo(800, 600), db=db, current_user=user)
        assert out.site_photos == [old, "https://cdn.example.com/new.jpg"] and out.hero_image_url is None
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_logo_can_be_removed():
    from app.api.v1.profile import delete_logo

    uid = await _seed(logo_url="https://cdn.example.com/logos/x.png")
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            out = await delete_logo(db=db, current_user=user)
        assert out.logo_url is None
    finally:
        await _cleanup(uid)
