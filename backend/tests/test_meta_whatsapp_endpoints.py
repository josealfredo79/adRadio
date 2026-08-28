"""Tests for /me/whatsapp-connection* endpoints."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.meta_whatsapp import MetaWhatsappConnectionOut
from app.services.meta_connect_service import ConnectionCheck
from app.services.meta_oauth_service import OAuthResult


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

    def test_save_without_app_credentials_keeps_legacy_flow(self, client, test_user):
        """PUT sin app_id/app_secret (Embedded Signup, número ya en Cloud API):
        no toca el App Secret ni configura webhook, y queda 'connected'."""
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()), \
                patch("app.api.v1.meta_whatsapp.configure_app_webhook", new=AsyncMock()) as mock_webhook:
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "real-token",
            })
            assert r.status_code == 200
            assert test_user.meta_connection_status == "connected"
            assert test_user.meta_app_secret_cipher is None
            mock_webhook.assert_not_called()

    def test_save_with_app_credentials_configures_webhook_and_connects(self, client, test_user):
        from app.services.meta_provisioning import ProvisionResult
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()), \
                patch("app.api.v1.meta_whatsapp.configure_app_webhook",
                      new=AsyncMock(return_value=ProvisionResult(ok=True))) as mock_webhook:
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "real-token",
                "app_id": "111222333", "app_secret": "the-secret",
            })
            assert r.status_code == 200
            data = r.json()
            assert test_user.meta_connection_status == "connected"
            assert test_user.meta_app_id == "111222333"
            assert test_user.meta_app_secret_cipher is not None
            assert test_user.meta_webhook_configured is True
            assert data["webhook_configured"] is True
            assert data["app_secret_set"] is True
            mock_webhook.assert_awaited_once_with("111222333", "the-secret")

    def test_save_with_app_credentials_webhook_failure_is_non_fatal_and_pending_setup(self, client, test_user):
        from app.services.meta_provisioning import ProvisionResult
        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()), \
                patch("app.api.v1.meta_whatsapp.configure_app_webhook",
                      new=AsyncMock(return_value=ProvisionResult(ok=False, code="invalid_credentials", message="Meta rechazó el App ID"))):
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "real-token",
                "app_id": "111222333", "app_secret": "bad-secret",
            })
            assert r.status_code == 200  # no es fatal
            data = r.json()
            assert test_user.meta_connection_status == "pending_setup"
            assert test_user.meta_webhook_configured is False
            assert data["webhook_configured"] is False
            assert "no se pudo configurar el webhook" in data["webhook_message"].lower()

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

    def test_resaving_same_number_with_no_prior_connected_at_stays_unrestricted(self, client, test_user):
        """Cuenta conectada desde antes de que existiera meta_connected_at
        (NULL) que refresca el token del MISMO número (ej. token vencido) no
        debe quedar retroactivamente atrapada en la rampa de warm-up — ese
        número ya lleva tiempo enviando sano."""
        test_user.meta_phone_number_id = "phone-1"
        test_user.meta_connected_at = None

        with patch("app.api.v1.meta_whatsapp.test_connection", new=AsyncMock(return_value=ConnectionCheck(
            ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()):
            r = client.put("/api/v1/me/whatsapp-connection", json={
                "waba_id": "waba-1", "phone_number_id": "phone-1", "token": "refreshed-token",
            })
            assert r.status_code == 200
            assert test_user.meta_connected_at is None

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


class TestEmbeddedConfig:
    def test_returns_disabled_when_not_configured(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.settings") as mock_settings:
            mock_settings.META_APP_ID = ""
            mock_settings.META_EMBEDDED_SIGNUP_CONFIG_ID = ""
            mock_settings.META_EMBEDDED_SIGNUP_ENABLED = True
            r = client.get("/api/v1/me/whatsapp-embedded-config")
            assert r.status_code == 200
            data = r.json()
            assert data["enabled"] is False

    def test_returns_disabled_when_configured_but_switch_off(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.settings") as mock_settings:
            mock_settings.META_APP_ID = "123456789"
            mock_settings.META_EMBEDDED_SIGNUP_CONFIG_ID = "cfg-123"
            mock_settings.META_EMBEDDED_SIGNUP_ENABLED = False
            r = client.get("/api/v1/me/whatsapp-embedded-config")
            assert r.status_code == 200
            data = r.json()
            assert data["enabled"] is False
            # app_id / config_id still exposed so the frontend can preload the SDK
            assert data["app_id"] == "123456789"

    def test_returns_enabled_when_configured_and_switch_on(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.settings") as mock_settings:
            mock_settings.META_APP_ID = "123456789"
            mock_settings.META_EMBEDDED_SIGNUP_CONFIG_ID = "cfg-123"
            mock_settings.META_EMBEDDED_SIGNUP_ENABLED = True
            r = client.get("/api/v1/me/whatsapp-embedded-config")
            assert r.status_code == 200
            data = r.json()
            assert data["enabled"] is True
            assert data["app_id"] == "123456789"
            assert data["config_id"] == "cfg-123"


class TestEmbeddedSignup:
    def test_missing_server_config_returns_422(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=AsyncMock(return_value=OAuthResult(
            ok=False, code="missing_config", message="META_APP_ID / META_APP_SECRET no están configurados en el servidor",
        ))):
            r = client.post("/api/v1/me/whatsapp-connection/embedded", json={
                "code": "abc123", "waba_id": "waba-1", "phone_number_id": "phone-1",
            })
            assert r.status_code == 422
            assert "no están configurados" in r.json()["detail"]

    def test_successful_embedded_signup_persists_and_subscribes(self, client, test_user):
        from app.api.v1.meta_whatsapp import get_whatsapp_connection
        with patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=AsyncMock(return_value=OAuthResult(
            ok=True, token="EAAGembeddedtoken", display_phone_number="+521234567890",
            verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()) as mock_subscribe, \
                patch("app.api.v1.meta_whatsapp.get_whatsapp_connection", new=AsyncMock(return_value=MetaWhatsappConnectionOut(
                    waba_id="waba-1", phone_number_id="phone-1", status="connected",
                    utility_template_status="not_configured",
                ))):
            r = client.post("/api/v1/me/whatsapp-connection/embedded", json={
                "code": "abc123", "waba_id": "waba-1", "phone_number_id": "phone-1",
            })
            assert r.status_code == 200
            assert test_user.meta_waba_id == "waba-1"
            assert test_user.meta_phone_number_id == "phone-1"
            assert test_user.meta_connection_status == "connected"
            assert test_user.meta_connected_at is not None
            assert mock_subscribe.await_count == 1
            mock_subscribe.assert_awaited_with("waba-1", "EAAGembeddedtoken")

    def test_exchange_failure_returns_422(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=AsyncMock(return_value=OAuthResult(
            ok=False, code="exchange_failed", message="Meta rechazó el código de autorización",
        ))):
            r = client.post("/api/v1/me/whatsapp-connection/embedded", json={
                "code": "bad", "waba_id": "waba-1", "phone_number_id": "phone-1",
            })
            assert r.status_code == 422
            assert test_user.meta_connection_status == "not_connected"
        assert test_user.meta_utility_template_status == "not_configured"
