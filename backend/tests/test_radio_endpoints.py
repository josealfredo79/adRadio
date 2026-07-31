"""Tests for radio.py — zero coverage existed before this file. This
router is a thin audio proxy (voice list + local/R2 file serving), no
DB models involved, so no real-DB seeding is needed here (unlike most
other router test files in this repo). Covers the path-traversal guard,
local-vs-R2 fallback branching, and the three R2 outcomes (success,
NoSuchKey -> 404, other error -> 502)."""
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1 import radio as radio_module
from app.api.v1.radio import list_voices, serve_audio


def _request(path: str = "/", host: str | None = None) -> Request:
    scope = {
        "type": "http", "method": "GET", "path": path, "headers": [],
        "client": (host or f"test-{uuid.uuid4()}", 123), "query_string": b"",
    }
    return Request(scope)


class TestListVoices:
    @pytest.mark.asyncio
    async def test_returns_available_voices(self):
        voices = await list_voices(request=_request())
        assert len(voices) == 8
        assert voices[0]["id"] == "es-MX-JorgeNeural"
        assert all({"id", "name", "lang", "gender", "provider"} <= v.keys() for v in voices)


class TestServeAudioValidation:
    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self):
        with pytest.raises(HTTPException) as exc_info:
            await serve_audio(request=_request(), filename="../../etc/passwd")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_absolute_path(self):
        with pytest.raises(HTTPException) as exc_info:
            await serve_audio(request=_request(), filename="/etc/passwd")
        assert exc_info.value.status_code == 400


class TestServeAudioLocal:
    @pytest.mark.asyncio
    async def test_serves_local_file_when_present(self, tmp_path):
        (tmp_path / "cache.mp3").write_bytes(b"fake-mp3-bytes")
        with patch.object(radio_module, "AUDIO_DIR", str(tmp_path)):
            response = await serve_audio(request=_request(), filename="cache.mp3")
        assert response.media_type == "audio/mpeg"
        assert response.path == str(tmp_path / "cache.mp3")


class TestServeAudioR2Fallback:
    @pytest.mark.asyncio
    async def test_r2_not_configured_returns_404(self, tmp_path):
        with patch.object(radio_module, "AUDIO_DIR", str(tmp_path)), \
             patch.object(radio_module.settings, "CF_R2_ACCESS_KEY", ""):
            with pytest.raises(HTTPException) as exc_info:
                await serve_audio(request=_request(), filename="missing.mp3")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_r2_missing_key_returns_404(self, tmp_path):
        error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        with patch.object(radio_module, "AUDIO_DIR", str(tmp_path)), \
             patch.object(radio_module.settings, "CF_R2_ACCESS_KEY", "fake-key"), \
             patch.object(radio_module, "_fetch_and_cache_from_r2", side_effect=error):
            with pytest.raises(HTTPException) as exc_info:
                await serve_audio(request=_request(), filename="missing.mp3")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_r2_other_error_returns_502(self, tmp_path):
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
        with patch.object(radio_module, "AUDIO_DIR", str(tmp_path)), \
             patch.object(radio_module.settings, "CF_R2_ACCESS_KEY", "fake-key"), \
             patch.object(radio_module, "_fetch_and_cache_from_r2", side_effect=error):
            with pytest.raises(HTTPException) as exc_info:
                await serve_audio(request=_request(), filename="missing.mp3")
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_r2_fallback_fetches_and_caches_locally(self, tmp_path):
        cached_path = tmp_path / "remote.mp3"

        def fake_fetch(filename, local_path):
            Path(local_path).write_bytes(b"from-r2")
            return "audio/mpeg"

        with patch.object(radio_module, "AUDIO_DIR", str(tmp_path)), \
             patch.object(radio_module.settings, "CF_R2_ACCESS_KEY", "fake-key"), \
             patch.object(radio_module, "_fetch_and_cache_from_r2", side_effect=fake_fetch):
            response = await serve_audio(request=_request(), filename="remote.mp3")
        assert response.media_type == "audio/mpeg"
        assert cached_path.read_bytes() == b"from-r2"
