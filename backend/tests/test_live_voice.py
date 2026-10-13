"""Voz en vivo con respaldo (2026-10-12): Microsoft bloqueó edge-tts (403) y la
mascota, el chat del cliente y el Copiloto se quedaban sin la voz del servidor
— el navegador ponía la suya, distinta. Ahora cae a Google y no reintenta
edge en cada frase."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.radio import tts


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(tts, "_edge_down_until", 0.0)
    monkeypatch.setattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", '{"type": "service_account"}')


@pytest.mark.asyncio
async def test_edge_works_uses_edge_and_never_google():
    google = AsyncMock(return_value=b"google")
    with patch.object(tts, "_tts_edge", AsyncMock(return_value=b"edge")) as edge, \
            patch.object(tts, "_tts_google_cloud", google):
        assert await tts.speak_voice("hola") == b"edge"
    edge.assert_awaited_once_with("hola", "es-MX-DaliaNeural", rate="+0%", pitch="+0Hz")
    google.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_blocked_falls_back_to_google_latina():
    with patch.object(tts, "_tts_edge", AsyncMock(side_effect=RuntimeError("403"))), \
            patch.object(tts, "_tts_google_cloud", AsyncMock(return_value=b"google")) as google:
        assert await tts.speak_voice("hola") == b"google"
    google.assert_awaited_once_with("hola", "es-US-Neural2-A")


@pytest.mark.asyncio
async def test_after_a_failure_edge_is_skipped_for_a_while():
    edge = AsyncMock(side_effect=RuntimeError("403"))
    with patch.object(tts, "_tts_edge", edge), \
            patch.object(tts, "_tts_google_cloud", AsyncMock(return_value=b"google")):
        await tts.speak_voice("uno")
        await tts.speak_voice("dos")
        await tts.speak_voice("tres")
    assert edge.await_count == 1  # no se pierden 200 ms en cada frase


@pytest.mark.asyncio
async def test_edge_tried_again_after_the_cooldown(monkeypatch):
    edge = AsyncMock(side_effect=[RuntimeError("403"), b"edge"])
    with patch.object(tts, "_tts_edge", edge), \
            patch.object(tts, "_tts_google_cloud", AsyncMock(return_value=b"google")):
        assert await tts.speak_voice("uno") == b"google"
        monkeypatch.setattr(tts, "_edge_down_until", 0.0)  # pasaron los 10 min
        assert await tts.speak_voice("dos") == b"edge"


@pytest.mark.asyncio
async def test_empty_edge_audio_counts_as_failure():
    with patch.object(tts, "_tts_edge", AsyncMock(return_value=b"")), \
            patch.object(tts, "_tts_google_cloud", AsyncMock(return_value=b"google")):
        assert await tts.speak_voice("hola") == b"google"


@pytest.mark.asyncio
async def test_no_voice_at_all_raises_so_the_browser_uses_its_own(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", "")
    with patch.object(tts, "_tts_edge", AsyncMock(side_effect=RuntimeError("403"))), \
            pytest.raises(RuntimeError):
        await tts.speak_voice("hola")
