"""Tests for /me/whatsapp-connection* endpoints."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.database import get_db
from app.services.meta_connect_service import ConnectionCheck


@pytest.fixture
def client(test_user):
    async def _fake_user():
        return test_user

    async def _fake_db():
        db = AsyncMock()
        yield db

    main_module.app.dependency_overrides[get_current_user] = _fake_user
    main_module.app.dependency_overrides[get_db] = _fake_db
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


class TestGetConnection:
    def test_not_connected_returns_status(self, client, test_user):
        r = client.get("/api/v1/me/whatsapp-connection")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "not_connected"
        assert data["token_last4"] is None

    def test_connected_redacts_token_to_last4(self, client, test_user):
        from app.core.crypto import encrypt_secret
        with patch("app.core.crypto.settings") as mock_crypto_settings:
            import base64
            key = base64.b64encode(b"0" * 32).decode()
            mock_crypto_settings.ENCRYPTION_KEY = key
            enc = encrypt_secret("EAAG1234567890ABCD")
            test_user.meta_token_cipher = enc.cipher
            test_user.meta_token_iv = enc.iv
            test_user.meta_token_tag = enc.tag
            test_user.meta_connection_status = "connected"
            test_user.meta_display_phone_number = "+521234567890"

            r = client.get("/api/v1/me/whatsapp-connection")
            assert r.status_code == 200
            assert r.json()["token_last4"] == "ABCD"


class TestConnectionTest:
    def test_valid_credentials_returns_ok_without_persisting(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))):
            r = client.post("/api/v1/me/whatsapp-connection/test", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "tok",
            })
            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is True
            assert data["display_phone_number"] == "+521234567890"
            # This is the test-only endpoint — must never write to the advertiser row.
            assert test_user.meta_connection_status == "not_connected"

    def test_invalid_token_returns_422(self, client):
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=False, code="invalid_token", message="El token no es válido",
        ))):
            r = client.post("/api/v1/me/whatsapp-connection/test", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "bad",
            })
            assert r.status_code == 422

    def test_meta_unavailable_returns_503(self, client):
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=False, code="meta_unavailable", message="Meta no disponible",
        ))):
            r = client.post("/api/v1/me/whatsapp-connection/test", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "tok",
            })
            assert r.status_code == 503

    def test_blank_field_returns_422(self, client):
        r = client.post("/api/v1/me/whatsapp-connection/test", json={
            "waba_id": "  ", "phone_number_id": "phone-1", "token": "tok",
        })
        assert r.status_code == 422


class TestSaveConnection:
    def test_save_re_validates_before_persisting(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()) as mock_subscribe:
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "real-token",
            })
            assert r.status_code == 200
            assert test_user.meta_connection_status == "connected"
            assert test_user.meta_phone_number_id == "phone-1"
            mock_subscribe.assert_called_once_with("waba-1", "real-token")

    def test_save_rejects_when_test_connection_fails(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=False, code="invalid_token", message="Token inválido",
        ))):
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "bad-token",
            })
            assert r.status_code == 422
            # Must not have been marked connected.
            assert test_user.meta_connection_status != "connected"

    def test_first_connection_sets_connected_at(self, client, test_user):
        """Capa 11: primera conexión (meta_phone_number_id era None) arranca
        la rampa de warm-up."""
        assert test_user.meta_connected_at is None
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()):
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "real-token",
            })
            assert r.status_code == 200
            assert test_user.meta_connected_at is not None

    def test_reconnecting_same_number_does_not_reset_warmup(self, client, test_user):
        """Refrescar el token del mismo número (ej. tras reconnect_required)
        no debe reiniciar la rampa de warm-up ya en curso."""
        from datetime import datetime, timedelta, timezone

        test_user.meta_phone_number_id = "phone-1"
        original_connected_at = datetime.now(timezone.utc) - timedelta(days=10)
        test_user.meta_connected_at = original_connected_at

        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()):
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "new-token",
            })
            assert r.status_code == 200
            assert test_user.meta_connected_at == original_connected_at

    def test_connecting_a_different_number_resets_warmup(self, client, test_user):
        """Cambiar a un número distinto (nuevo phone_number_id) sí reinicia
        la rampa — Meta lo trata como un número nuevo sin historial."""
        from datetime import datetime, timedelta, timezone

        test_user.meta_phone_number_id = "phone-old"
        test_user.meta_connected_at = datetime.now(timezone.utc) - timedelta(days=30)

        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()):
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-new", "token": "real-token",
            })
            assert r.status_code == 200
            assert test_user.meta_connected_at > datetime.now(timezone.utc) - timedelta(minutes=1)


class TestUpdateTemplates:
    def test_setting_utility_template_marks_approved(self, client, test_user):
        r = client.patch("/api/v1/me/whatsapp-templates", json={"utility_template_name": "notificacion_v2"})
        assert r.status_code == 200
        assert test_user.meta_utility_template_name == "notificacion_v2"
        assert test_user.meta_utility_template_status == "approved"

    def test_clearing_utility_template_marks_not_configured(self, client, test_user):
        r = client.patch("/api/v1/me/whatsapp-templates", json={"utility_template_name": ""})
        assert r.status_code == 200
        assert test_user.meta_utility_template_name is None
        assert test_user.meta_utility_template_status == "not_configured"
