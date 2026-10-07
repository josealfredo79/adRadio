"""
send_welcome_cuna must send WhatsApp the audio URL exactly as storage returned
it. It used to rebuild the URL by splitting on the first "/radio/" — which is
the one in /api/v1/radio/ — so "audio" came out doubled, Meta got a 404 and
the cuña failed with 131053 (2026-10-07, first lead on the central number).
"""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers.tasks import send_welcome_cuna

AUDIO_URL = "https://www.iaradio.online/api/v1/radio/audio/radio/iaradio_680815de.ogg"


def _db_with_advertiser(advertiser):
    db = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    result = MagicMock()
    result.scalar_one_or_none.return_value = advertiser
    db.execute = AsyncMock(return_value=result)
    return db


def test_sends_the_storage_url_unchanged():
    advertiser = MagicMock()
    send = AsyncMock()

    with patch("app.services.radio_service.generate_radio_ad", AsyncMock(return_value=AUDIO_URL)), \
         patch("app.services.meta_service.send_whatsapp_media", send), \
         patch("app.database.CeleryAsyncSessionLocal", return_value=_db_with_advertiser(advertiser)), \
         patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
        send_welcome_cuna(str(uuid.uuid4()), "+5219515199084", "IARadio")

    send.assert_awaited_once()
    assert send.await_args.args[1] == AUDIO_URL
    assert "/audio/audio/" not in send.await_args.args[1]
