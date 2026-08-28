"""Tests for the Meta WhatsApp webhook (handshake, signature, routing)."""
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture
def client():
    return TestClient(main_module.app)


class TestHandshake:
    def test_valid_verify_token_echoes_challenge(self, client):
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_WEBHOOK_VERIFY_TOKEN = "correct-token"
            r = client.get("/api/v1/webhooks/meta", params={
                "hub.mode": "subscribe",
                "hub.verify_token": "correct-token",
                "hub.challenge": "challenge-echo-123",
            })
            assert r.status_code == 200
            assert r.text == "challenge-echo-123"

    def test_wrong_verify_token_returns_403(self, client):
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_WEBHOOK_VERIFY_TOKEN = "correct-token"
            r = client.get("/api/v1/webhooks/meta", params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "x",
            })
            assert r.status_code == 403

    def test_wrong_mode_returns_403(self, client):
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_WEBHOOK_VERIFY_TOKEN = "correct-token"
            r = client.get("/api/v1/webhooks/meta", params={
                "hub.mode": "unsubscribe",
                "hub.verify_token": "correct-token",
                "hub.challenge": "x",
            })
            assert r.status_code == 403


class TestSignatureValidation:
    def test_no_app_secret_configured_skips_check(self, client):
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            r = client.post("/api/v1/webhooks/meta", json={"entry": []})
            assert r.status_code == 200

    def test_valid_signature_accepted(self, client):
        body = json.dumps({"entry": []}).encode()
        secret = "my-app-secret"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = secret
            r = client.post(
                "/api/v1/webhooks/meta",
                content=body,
                headers={"content-type": "application/json", "X-Hub-Signature-256": sig},
            )
            assert r.status_code == 200
            assert r.json() == {"received": True}

    def test_invalid_signature_rejected_but_still_200(self, client):
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = "my-app-secret"
            r = client.post(
                "/api/v1/webhooks/meta",
                content=b'{"entry": []}',
                headers={"content-type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
            )
            # Meta requires 200 even on rejection, to avoid the subscription
            # being auto-disabled — but the payload must NOT have been processed.
            assert r.status_code == 200

    def test_malformed_json_still_returns_200(self, client):
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            r = client.post(
                "/api/v1/webhooks/meta",
                content=b"not-valid-json{{{",
                headers={"content-type": "application/json"},
            )
            assert r.status_code == 200
            assert r.json() == {"received": True}


class TestRouting:
    def test_unknown_phone_number_id_does_not_crash(self, client):
        """Uses the real DB session (no advertiser will match a made-up
        phone_number_id) — exercises the actual query + graceful no-op path,
        matching how this was manually verified against production data."""
        payload = {
            "entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "does-not-exist-999999999"},
                "messages": [{"from": "5215599631448", "id": "wamid.1", "type": "text", "text": {"body": "hola"}}],
            }}]}]
        }
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            r = client.post("/api/v1/webhooks/meta", json=payload)
        assert r.status_code == 200
        assert r.json() == {"received": True}

    def test_non_messages_field_is_ignored(self, client):
        payload = {"entry": [{"changes": [{"field": "account_alerts", "value": {}}]}]}
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            r = client.post("/api/v1/webhooks/meta", json=payload)
        assert r.status_code == 200

    def test_status_update_without_messages_applies_status_and_returns(self, client):
        payload = {
            "entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-1"},
                "statuses": [{"id": "wamid.999", "status": "delivered"}],
            }}]}]
        }
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            with patch(
                "app.api.v1.webhooks_pkg.meta_incoming.apply_status_update", new=AsyncMock()
            ) as mock_apply:
                r = client.post("/api/v1/webhooks/meta", json=payload)
        assert r.status_code == 200
        mock_apply.assert_called_once_with(mock_apply.call_args.args[0], "wamid.999", "delivered", None)


async def _seed_advertiser_with_running_campaign(waba_id: str):
    """Real DB session (same pattern as test_modules.py) — creates an
    advertiser + a running campaign under the given WABA id.

    Disposes the shared engine pool first: this file also has sync
    TestClient-based tests, each spinning its own event loop, and asyncpg
    connections are loop-bound — a pooled connection left over from one of
    those would crash ("attached to a different loop") the moment this
    async test's own loop tries to reuse it.
    """
    import uuid

    from app.database import AsyncSessionLocal, engine
    from app.models.campaign import Campaign
    from app.models.user import User

    await engine.dispose()

    async with AsyncSessionLocal() as db:
        advertiser = User(
            email=f"{uuid.uuid4()}@test.com",
            password_hash="x",
            business_name="Test",
            meta_waba_id=waba_id,
        )
        db.add(advertiser)
        await db.flush()
        campaign = Campaign(
            advertiser_id=advertiser.id,
            name="Promo",
            type="promo",
            message_text="hola",
            status="running",
        )
        db.add(campaign)
        await db.commit()
        return advertiser.id, campaign.id


class TestPhoneNumberQualityUpdate:
    @pytest.mark.asyncio
    async def test_flagged_event_pauses_active_campaigns(self):
        """Uses the real DB session end-to-end (httpx AsyncClient over the
        real ASGI app, same event loop as the DB session — not the sync
        TestClient, which runs requests in a different loop and would break
        the asyncpg connection pool): creates an advertiser + a running
        campaign, sends a FLAGGED quality update for that WABA, and checks
        the campaign actually got paused and the rating got stored — not
        just that the handler was called."""
        import uuid

        from httpx import ASGITransport, AsyncClient

        from app.database import AsyncSessionLocal
        from app.models.campaign import Campaign
        from app.models.user import User

        waba_id = f"waba-{uuid.uuid4()}"
        advertiser_id, campaign_id = await _seed_advertiser_with_running_campaign(waba_id)

        payload = {
            "entry": [{
                "id": waba_id,
                "changes": [{
                    "field": "phone_number_quality_update",
                    "value": {"event": "FLAGGED", "current_limit": "TIER_50", "display_phone_number": "5215599631448"},
                }],
            }],
        }
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            transport = ASGITransport(app=main_module.app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/api/v1/webhooks/meta", json=payload)
        assert r.status_code == 200

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            campaign = await db.get(Campaign, campaign_id)
            assert advertiser.meta_quality_rating == "RED"
            assert advertiser.meta_messaging_tier == "TIER_50"
            assert campaign.status == "paused"

    @pytest.mark.asyncio
    async def test_unflagged_event_updates_rating_without_pausing(self):
        import uuid

        from httpx import ASGITransport, AsyncClient

        from app.database import AsyncSessionLocal
        from app.models.campaign import Campaign
        from app.models.user import User

        waba_id = f"waba-{uuid.uuid4()}"
        advertiser_id, campaign_id = await _seed_advertiser_with_running_campaign(waba_id)

        payload = {
            "entry": [{
                "id": waba_id,
                "changes": [{
                    "field": "phone_number_quality_update",
                    "value": {"event": "UNFLAGGED", "current_limit": "TIER_1K"},
                }],
            }],
        }
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            transport = ASGITransport(app=main_module.app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/api/v1/webhooks/meta", json=payload)
        assert r.status_code == 200

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            campaign = await db.get(Campaign, campaign_id)
            assert advertiser.meta_quality_rating == "GREEN"
            assert campaign.status == "running"

    def test_unknown_waba_does_not_crash(self, client):
        payload = {
            "entry": [{
                "id": "does-not-exist",
                "changes": [{
                    "field": "phone_number_quality_update",
                    "value": {"event": "FLAGGED", "current_limit": "TIER_50"},
                }],
            }],
        }
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            r = client.post("/api/v1/webhooks/meta", json=payload)
        assert r.status_code == 200
        assert r.json() == {"received": True}


class TestPerAdvertiserSignature:
    """`_validate_signature` accepts a payload signed with the advertiser's own
    Meta App Secret (manual self-service flow), falls back to the global
    META_APP_SECRET, and to trusting the URL when neither is available."""

    def _sig(self, secret: str, body: bytes) -> str:
        return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    @pytest.mark.asyncio
    async def test_accepts_signature_from_advertiser_app_secret(self):
        from app.api.v1.webhooks_pkg import meta_incoming

        body = json.dumps({"entry": [{"id": "waba-9"}]}).encode()
        with patch.object(meta_incoming, "settings") as s, patch.object(
            meta_incoming, "_advertiser_app_secret", new=AsyncMock(return_value="adv-secret")
        ):
            s.META_APP_SECRET = "global-secret"
            ok = await meta_incoming._validate_signature(
                AsyncMock(), body, self._sig("adv-secret", body), json.loads(body)
            )
        assert ok is True

    @pytest.mark.asyncio
    async def test_falls_back_to_global_secret(self):
        from app.api.v1.webhooks_pkg import meta_incoming

        body = json.dumps({"entry": [{"id": "waba-9"}]}).encode()
        with patch.object(meta_incoming, "settings") as s, patch.object(
            meta_incoming, "_advertiser_app_secret", new=AsyncMock(return_value=None)
        ):
            s.META_APP_SECRET = "global-secret"
            ok = await meta_incoming._validate_signature(
                AsyncMock(), body, self._sig("global-secret", body), json.loads(body)
            )
        assert ok is True

    @pytest.mark.asyncio
    async def test_rejects_when_advertiser_secret_present_but_signature_forged(self):
        from app.api.v1.webhooks_pkg import meta_incoming

        body = json.dumps({"entry": [{"id": "waba-9"}]}).encode()
        with patch.object(meta_incoming, "settings") as s, patch.object(
            meta_incoming, "_advertiser_app_secret", new=AsyncMock(return_value="adv-secret")
        ):
            s.META_APP_SECRET = ""
            ok = await meta_incoming._validate_signature(
                AsyncMock(), body, "sha256=deadbeef", json.loads(body)
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_trusts_when_no_secret_available_and_no_header(self):
        from app.api.v1.webhooks_pkg import meta_incoming

        body = b'{"entry": []}'
        with patch.object(meta_incoming, "settings") as s:
            s.META_APP_SECRET = ""
            ok = await meta_incoming._validate_signature(AsyncMock(), body, "", json.loads(body))
        assert ok is True


class TestAccountAlerts:
    def test_account_alert_is_logged_and_acked(self, client):
        payload = {
            "entry": [{
                "id": "waba-123",
                "changes": [{
                    "field": "account_alerts",
                    "value": {"alert_type": "INCREASED_CAPABILITIES_ELIGIBILITY_FAILED", "alert_description": "x"},
                }],
            }],
        }
        with patch("app.api.v1.webhooks_pkg.meta_incoming.settings") as mock_settings:
            mock_settings.META_APP_SECRET = ""
            r = client.post("/api/v1/webhooks/meta", json=payload)
        assert r.status_code == 200
        assert r.json() == {"received": True}


class TestExtractBodyText:
    def test_text_message(self):
        from app.api.v1.webhooks_pkg.meta_incoming import _extract_body_text
        body, media_id = _extract_body_text({"type": "text", "text": {"body": "  hola  "}})
        assert body == "hola"
        assert media_id is None

    def test_audio_message_returns_media_id(self):
        from app.api.v1.webhooks_pkg.meta_incoming import _extract_body_text
        body, media_id = _extract_body_text({"type": "audio", "audio": {"id": "media-123"}})
        assert body == ""
        assert media_id == "media-123"

    def test_button_reply(self):
        from app.api.v1.webhooks_pkg.meta_incoming import _extract_body_text
        body, media_id = _extract_body_text({"type": "button", "button": {"text": "1"}})
        assert body == "1"

    def test_interactive_button_reply(self):
        from app.api.v1.webhooks_pkg.meta_incoming import _extract_body_text
        body, _ = _extract_body_text({
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"title": "Confirmar"}},
        })
        assert body == "Confirmar"

    def test_unsupported_type_falls_back_to_placeholder(self):
        from app.api.v1.webhooks_pkg.meta_incoming import _extract_body_text
        body, media_id = _extract_body_text({"type": "sticker"})
        assert body == "[media:sticker]"
        assert media_id is None
