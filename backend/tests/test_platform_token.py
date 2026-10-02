"""Token del número central (platform_whatsapp.platform_token): si no hay
IARADIO_WA_TOKEN, se usa el que ya tiene guardado (cifrado) la cuenta cuyo bot
es ese mismo número — el chip de IaRadio es también el bot de la cuenta
IaRadio, así el secreto no se copia a otro lado. BD real (.env.test)."""
import uuid

import pytest
from sqlalchemy import delete

from app.core.crypto import encrypt_secret
from app.database import AsyncSessionLocal, engine
from app.models.user import User
from app.services import platform_whatsapp as pw


@pytest.fixture(autouse=True)
def _fresh_cache():
    pw._token_cache = (None, 0.0)
    yield
    pw._token_cache = (None, 0.0)


@pytest.mark.asyncio
async def test_uses_the_token_stored_for_the_number(monkeypatch):
    number_id = f"test-{uuid.uuid4().hex[:12]}"
    enc = encrypt_secret("EAAG-token-de-la-cuenta")
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", meta_phone_number_id=number_id,
                    meta_token_cipher=enc.cipher, meta_token_iv=enc.iv, meta_token_tag=enc.tag)
        db.add(user)
        await db.commit()
        uid = user.id
    try:
        monkeypatch.setattr(pw.settings, "IARADIO_WA_PHONE_NUMBER_ID", number_id)
        monkeypatch.setattr(pw.settings, "IARADIO_WA_TOKEN", "")
        assert pw.platform_enabled()
        assert await pw.platform_token() == "EAAG-token-de-la-cuenta"
        # Si está la variable, manda la variable.
        monkeypatch.setattr(pw.settings, "IARADIO_WA_TOKEN", "tok-env")
        assert await pw.platform_token() == "tok-env"
    finally:
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_no_account_for_the_number_means_not_configured(monkeypatch):
    monkeypatch.setattr(pw.settings, "IARADIO_WA_PHONE_NUMBER_ID", f"nadie-{uuid.uuid4().hex[:8]}")
    monkeypatch.setattr(pw.settings, "IARADIO_WA_TOKEN", "")
    await engine.dispose()
    assert await pw.platform_token() is None
    assert await pw.send_platform_text("+5215511111111", "hola") == (None, "platform_not_configured")
    await engine.dispose()
