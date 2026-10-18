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
from app.services.meta_provisioning import ProvisionResult


@pytest.fixture(autouse=True)
def _meta_does_not_know_if_on_business_app():
    # Nunca llamar a Meta en estas pruebas; cada caso que lo necesite lo cambia.
    with patch("app.services.coexistence_service.is_on_business_app", new=AsyncMock(return_value=None)):
        yield


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
            mock_settings.META_EMBEDDED_SIGNUP_ADMINS_ONLY = False
            r = client.get("/api/v1/me/whatsapp-embedded-config")
            assert r.status_code == 200
            data = r.json()
            assert data["enabled"] is True
            assert data["app_id"] == "123456789"
            assert data["config_id"] == "cfg-123"


class TestEmbeddedSignup:
    @pytest.fixture(autouse=True)
    def _button_on_for_everyone(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "META_APP_ID", "123456789")
        monkeypatch.setattr(settings, "META_EMBEDDED_SIGNUP_CONFIG_ID", "cfg-123")
        monkeypatch.setattr(settings, "META_EMBEDDED_SIGNUP_ENABLED", True)
        monkeypatch.setattr(settings, "META_EMBEDDED_SIGNUP_ADMINS_ONLY", False, raising=False)

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
        with patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=AsyncMock(return_value=OAuthResult(
            ok=True, token="EAAGembeddedtoken", waba_id="waba-1", phone_number_id="phone-1",
            display_phone_number="+521234567890", verified_name="Mi Negocio",
        ))), patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()) as mock_subscribe, \
                patch("app.api.v1.meta_whatsapp.register_phone_number", new=AsyncMock(
                    return_value=ProvisionResult(ok=True, data={"success": True}),
                )) as mock_register, \
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
            # Registered on the Cloud API with a fresh 6-digit PIN, kept encrypted.
            phone_id, token, pin = mock_register.await_args.args
            assert (phone_id, token) == ("phone-1", "EAAGembeddedtoken")
            assert len(pin) == 6 and pin.isdigit()
            assert test_user.meta_verification_status == "registered"
            assert test_user.meta_pin_cipher

    def _signup(self, client, oauth: OAuthResult, registration: ProvisionResult, body: dict):
        with patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=AsyncMock(return_value=oauth)) as mock_exchange, \
                patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()) as mock_subscribe, \
                patch("app.api.v1.meta_whatsapp.register_phone_number", new=AsyncMock(return_value=registration)):
            r = client.post("/api/v1/me/whatsapp-connection/embedded", json=body)
        return r, mock_exchange, mock_subscribe

    def test_missing_ids_use_the_ones_resolved_from_the_token(self, client, test_user):
        r, mock_exchange, mock_subscribe = self._signup(
            client,
            OAuthResult(ok=True, token="tok", waba_id="waba-9", phone_number_id="phone-9", display_phone_number="+52155"),
            ProvisionResult(ok=True),
            {"code": "abc123"},
        )
        assert r.status_code == 200
        mock_exchange.assert_awaited_with("abc123", "", "")
        assert test_user.meta_waba_id == "waba-9"
        assert test_user.meta_phone_number_id == "phone-9"
        mock_subscribe.assert_awaited_with("waba-9", "tok")

    def test_registration_failure_still_connects_but_flags_it(self, client, test_user):
        r, _, _ = self._signup(
            client,
            OAuthResult(ok=True, token="tok", waba_id="waba-1", phone_number_id="phone-1"),
            ProvisionResult(ok=False, code="meta_error", message="nope"),
            {"code": "abc123", "waba_id": "waba-1", "phone_number_id": "phone-1"},
        )
        assert r.status_code == 200
        assert test_user.meta_connection_status == "connected"
        assert test_user.meta_verification_status == "register_failed"
        assert not test_user.meta_pin_cipher

    def test_already_registered_number_keeps_its_owner_pin(self, client, test_user):
        r, _, _ = self._signup(
            client,
            OAuthResult(ok=True, token="tok", waba_id="waba-1", phone_number_id="phone-1"),
            ProvisionResult(ok=True, data={"already_registered": True}),
            {"code": "abc123", "waba_id": "waba-1", "phone_number_id": "phone-1"},
        )
        assert r.status_code == 200
        assert test_user.meta_verification_status == "registered"
        # Our PIN never took effect, so don't store it.
        assert not test_user.meta_pin_cipher

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


class TestMetaTemplates:
    @pytest.fixture
    def connected(self, test_user):
        test_user.meta_waba_id = "waba-1"
        with patch("app.api.v1.meta_whatsapp._connection", return_value=("phone-1", "tok")):
            yield test_user

    def test_requires_connection(self, client, test_user):
        with patch("app.api.v1.meta_whatsapp._connection", return_value=None):
            r = client.get("/api/v1/me/whatsapp-templates/meta")
        assert r.status_code == 409

    def test_lists_templates(self, client, connected):
        from app.services.meta_templates import TemplateSummary
        with patch("app.api.v1.meta_whatsapp.list_templates", new=AsyncMock(return_value=(
            [TemplateSummary(id="1", name="aviso", language="es_MX", category="UTILITY", status="APPROVED", body="Hola")],
            None,
        ))) as mock_list:
            r = client.get("/api/v1/me/whatsapp-templates/meta")
        assert r.status_code == 200
        assert r.json()[0]["name"] == "aviso"
        mock_list.assert_awaited_with("waba-1", "tok")

    def test_creates_template(self, client, connected):
        from app.services.meta_templates import TemplateResult
        with patch("app.api.v1.meta_whatsapp.create_template", new=AsyncMock(return_value=TemplateResult(
            ok=True, data={"id": "tpl-9", "status": "PENDING", "category": "UTILITY"},
        ))) as mock_create:
            r = client.post("/api/v1/me/whatsapp-templates/meta", json={
                "name": "Recordatorio Cita", "category": "UTILITY",
                "body": "Hola {{1}}, te esperamos mañana.", "examples": ["Ana"],
            })
        assert r.status_code == 201
        assert r.json() == {
            "id": "tpl-9", "name": "recordatorio_cita", "language": "es_MX", "category": "UTILITY",
            "status": "PENDING", "body": "Hola {{1}}, te esperamos mañana.", "rejected_reason": None,
        }
        args, kwargs = mock_create.await_args
        assert args == ("waba-1", "tok")
        assert kwargs["name"] == "recordatorio_cita"
        assert kwargs["components"][0]["example"] == {"body_text": [["Ana"]]}

    def test_invalid_template_never_reaches_meta(self, client, connected):
        with patch("app.api.v1.meta_whatsapp.create_template", new=AsyncMock()) as mock_create:
            r = client.post("/api/v1/me/whatsapp-templates/meta", json={
                "name": "aviso", "category": "UTILITY", "body": "Hola {{1}} ya", "examples": [],
            })
        assert r.status_code == 422
        assert "ejemplo" in r.json()["detail"]
        mock_create.assert_not_awaited()

    def test_meta_rejection_is_422_with_its_reason(self, client, connected):
        from app.services.meta_templates import TemplateResult
        with patch("app.api.v1.meta_whatsapp.create_template", new=AsyncMock(return_value=TemplateResult(
            ok=False, code="meta_error", message="Ya existe una plantilla con ese nombre",
        ))):
            r = client.post("/api/v1/me/whatsapp-templates/meta", json={
                "name": "aviso", "category": "UTILITY", "body": "Hola ya abrimos",
            })
        assert r.status_code == 422
        assert r.json()["detail"] == "Ya existe una plantilla con ese nombre"


# docs/specs/2026-10-12-conectar-con-meta.md — encender el botón con cuidado.
def _settings(mock, enabled=True, admins_only=True, testers=""):
    mock.META_APP_ID = "123456789"
    mock.META_EMBEDDED_SIGNUP_CONFIG_ID = "cfg-123"
    mock.META_EMBEDDED_SIGNUP_ENABLED = enabled
    mock.META_EMBEDDED_SIGNUP_ADMINS_ONLY = admins_only
    mock.META_EMBEDDED_SIGNUP_TEST_EMAILS = testers
    mock.IARADIO_WA_PHONE_NUMBER_ID = "central-1"


class TestEmbeddedRollout:
    def _enabled(self, client, test_user, role, **kw):
        test_user.role = role
        with patch("app.api.v1.meta_whatsapp.settings") as s:
            _settings(s, **kw)
            return client.get("/api/v1/me/whatsapp-embedded-config").json()["enabled"]

    def test_caso1_switch_off_hides_it_even_from_admins(self, client, test_user):
        assert self._enabled(client, test_user, "admin", enabled=False) is False

    def test_caso2_admins_only_mode(self, client, test_user):
        assert self._enabled(client, test_user, "admin") is True
        assert self._enabled(client, test_user, "advertiser") is False

    def test_caso3_everyone_mode(self, client, test_user):
        assert self._enabled(client, test_user, "advertiser", admins_only=False) is True

    def test_caso4_server_refuses_connection_when_not_enabled_for_user(self, client, test_user):
        test_user.role = "advertiser"
        exchange = AsyncMock()
        with patch("app.api.v1.meta_whatsapp.settings") as s, \
                patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=exchange):
            _settings(s)
            r = client.post("/api/v1/me/whatsapp-connection/embedded", json={"code": "abc"})
        assert r.status_code == 403
        exchange.assert_not_awaited()

    def _connect(self, client, test_user, phone_number_id="phone-1"):
        test_user.role = "admin"
        with patch("app.api.v1.meta_whatsapp.settings") as s, \
                patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=AsyncMock(return_value=OAuthResult(
                    ok=True, token="tok", waba_id="waba-1", phone_number_id=phone_number_id))), \
                patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()), \
                patch("app.api.v1.meta_whatsapp.register_phone_number",
                      new=AsyncMock(return_value=ProvisionResult(ok=True))):
            _settings(s)
            return client.post("/api/v1/me/whatsapp-connection/embedded", json={"code": "abc"})

    def test_caso6_same_number_keeps_the_anti_ban_ramp(self, client, test_user):
        from datetime import datetime, timezone
        before = datetime(2026, 9, 1, tzinfo=timezone.utc)
        test_user.meta_phone_number_id = "phone-1"
        test_user.meta_connected_at = before
        assert self._connect(client, test_user, "phone-1").status_code == 200
        assert test_user.meta_connected_at == before

    def test_caso6_new_number_restarts_the_ramp(self, client, test_user):
        from datetime import datetime, timezone
        before = datetime(2026, 9, 1, tzinfo=timezone.utc)
        test_user.meta_phone_number_id = "phone-viejo"
        test_user.meta_connected_at = before
        assert self._connect(client, test_user, "phone-1").status_code == 200
        assert test_user.meta_connected_at > before

    def test_caso7_old_own_app_is_forgotten(self, client, test_user):
        test_user.meta_app_id = "app-propia"
        test_user.meta_app_secret_cipher = "c"
        test_user.meta_app_secret_iv = "i"
        test_user.meta_app_secret_tag = "t"
        test_user.meta_webhook_configured = True
        assert self._connect(client, test_user).status_code == 200
        assert test_user.meta_app_id is None
        assert test_user.meta_app_secret_cipher is None
        assert test_user.meta_webhook_configured is False

    def test_caso9_central_number_account_never_sees_or_uses_it(self, client, test_user):
        # La cuenta IaRadio (número central): reemplazarlo tumbaría ventas, códigos y Copiloto.
        test_user.meta_phone_number_id = "central-1"
        assert self._enabled(client, test_user, "admin", admins_only=False) is False
        exchange = AsyncMock()
        with patch("app.api.v1.meta_whatsapp.settings") as s, \
                patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=exchange):
            _settings(s, admins_only=False)
            r = client.post("/api/v1/me/whatsapp-connection/embedded", json={"code": "abc"})
        assert r.status_code == 403 and "número central" in r.json()["detail"]
        exchange.assert_not_awaited()

    def test_caso10_test_emails_see_it_in_admins_only_mode(self, client, test_user):
        test_user.email = "Prueba@IaRadio.online"
        assert self._enabled(client, test_user, "advertiser", testers="otro@x.com, prueba@iaradio.online") is True
        assert self._enabled(client, test_user, "advertiser", testers="otro@x.com") is False


# docs/specs/2026-10-12-coexistencia.md
class TestEmbeddedCoexistence:
    @pytest.fixture(autouse=True)
    def _button_on(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "META_APP_ID", "123456789")
        monkeypatch.setattr(settings, "META_EMBEDDED_SIGNUP_CONFIG_ID", "cfg-123")
        monkeypatch.setattr(settings, "META_EMBEDDED_SIGNUP_ENABLED", True)
        monkeypatch.setattr(settings, "META_EMBEDDED_SIGNUP_ADMINS_ONLY", False)

    def _connect(self, client, coexistence, sync=None):
        register = AsyncMock(return_value=ProvisionResult(ok=True))
        sync = sync or AsyncMock(return_value={"smb_app_state_sync": "r1", "history": "r2"})
        with patch("app.api.v1.meta_whatsapp.exchange_embedded_code", new=AsyncMock(return_value=OAuthResult(
                    ok=True, token="tok", waba_id="waba-1", phone_number_id="phone-1"))), \
                patch("app.api.v1.meta_whatsapp.subscribe_app_to_waba", new=AsyncMock()), \
                patch("app.api.v1.meta_whatsapp.register_phone_number", new=register), \
                patch("app.services.coexistence_service.request_initial_sync", new=sync):
            r = client.post("/api/v1/me/whatsapp-connection/embedded",
                            json={"code": "abc", "waba_id": "waba-1", "coexistence": coexistence})
        return r, register, sync

    def test_caso2_business_app_number_connects_without_registering(self, client, test_user):
        r, register, _ = self._connect(client, True)
        assert r.status_code == 200 and r.json()["coexistence"] is True
        register.assert_not_awaited()  # Meta prohíbe volver a registrarlo
        assert test_user.meta_coexistence is True
        assert test_user.meta_verification_status == "registered"
        assert test_user.meta_connection_status == "connected"

    def test_caso2_new_number_still_registers(self, client, test_user):
        r, register, sync = self._connect(client, False)
        assert r.status_code == 200 and r.json()["coexistence"] is False
        register.assert_awaited_once()
        sync.assert_not_awaited()
        assert test_user.meta_coexistence is False

    def test_caso3_contacts_and_history_requested_right_away(self, client, test_user):
        _, _, sync = self._connect(client, True)
        sync.assert_awaited_once_with("phone-1", "tok")

    def test_caso3_sync_failure_keeps_the_connection(self, client, test_user):
        failing = AsyncMock(return_value={"smb_app_state_sync": "error: x", "history": "error: y"})
        r, _, _ = self._connect(client, True, sync=failing)
        assert r.status_code == 200
        assert test_user.meta_connection_status == "connected"

    def test_caso2_meta_says_business_app_even_if_browser_missed_it(self, client, test_user):
        # El aviso del navegador se perdió (coexistence=false), pero Meta dice
        # que el número está en la app Business: no se registra.
        with patch("app.services.coexistence_service.is_on_business_app", new=AsyncMock(return_value=True)):
            r, register, sync = self._connect(client, False)
        assert r.status_code == 200 and r.json()["coexistence"] is True
        register.assert_not_awaited()
        sync.assert_awaited_once()


class TestInitialSyncCall:
    @pytest.mark.asyncio
    async def test_caso3_asks_meta_for_contacts_then_history(self):
        import httpx

        from app.services.coexistence_service import request_initial_sync

        calls = []

        def handler(request: httpx.Request):
            import json as _json
            calls.append((request.url.path, _json.loads(request.content)["sync_type"],
                          request.headers["Authorization"]))
            return httpx.Response(200, json={"request_id": f"req-{len(calls)}"})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        with patch("httpx.AsyncClient", lambda **kw: real_client(transport=transport)):
            out = await request_initial_sync("phone-1", "tok")
        assert [c[1] for c in calls] == ["smb_app_state_sync", "history"]
        assert all(c[0].endswith("/phone-1/smb_app_data") and c[2] == "Bearer tok" for c in calls)
        assert out == {"smb_app_state_sync": "req-1", "history": "req-2"}

    @pytest.mark.asyncio
    async def test_caso3_meta_error_is_reported_not_raised(self):
        import httpx

        from app.services.coexistence_service import request_initial_sync

        transport = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"message": "fuera de las 24 h"}}))
        real_client = httpx.AsyncClient
        with patch("httpx.AsyncClient", lambda **kw: real_client(transport=transport)):
            out = await request_initial_sync("phone-1", "tok")
        assert out["history"] == "error: fuera de las 24 h"


class TestMetaSinFriccion:
    """docs/specs/2026-10-17-meta-sin-friccion.md"""

    def test_caso5_config_tells_the_real_meta_pricing(self, client, test_user):
        from app.config import settings
        data = client.get("/api/v1/me/whatsapp-embedded-config").json()
        assert data["free_service_messages"] == settings.META_FREE_SERVICE_MESSAGES
        assert data["service_price_mxn"] == settings.META_SERVICE_PRICE_MXN

    def test_caso2_help_endpoint_saves_the_request(self, client, test_user):
        with patch("app.services.meta_help_request.request_whatsapp_help", new=AsyncMock(return_value=True)) as req:
            r = client.post("/api/v1/me/whatsapp-connection/help")
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert req.await_args.args[1] is test_user

    def test_help_without_phone_explains_what_to_fill(self, client, test_user):
        with patch("app.services.meta_help_request.request_whatsapp_help", new=AsyncMock(return_value=False)):
            r = client.post("/api/v1/me/whatsapp-connection/help")
        assert r.status_code == 422 and "WhatsApp personal" in r.json()["detail"]
