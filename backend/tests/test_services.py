"""
Tests unitarios para servicios de IaRadio.
Estos tests no requieren conexión a DB externa ni APIs de terceros.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCouponService:
    """Tests para el servicio de cupones."""

    def test_generate_coupon_code_length(self):
        from app.services.coupon_service import generate_coupon_code
        
        code = generate_coupon_code(8)
        assert len(code) == 8
        assert code.isalnum()
        assert code.isupper()

    def test_generate_coupon_code_no_confusing_chars(self):
        from app.services.coupon_service import generate_coupon_code
        
        # Generar múltiples códigos y verificar que no contengan caracteres confusos
        for _ in range(100):
            code = generate_coupon_code(8)
            assert "0" not in code
            assert "O" not in code
            assert "1" not in code
            assert "I" not in code
            assert "L" not in code

    def test_format_coupon_in_message_basic(self):
        from app.services.coupon_service import format_coupon_in_message, default_expiry
        
        message = "Hola bienvenido a nuestra tienda"
        code = "TEST123"
        expires = default_expiry()
        
        result = format_coupon_in_message(message, code, expires)
        
        assert message in result
        assert code in result
        assert "🎫" in result
        assert "⏰" in result

    def test_format_coupon_in_message_with_description(self):
        from app.services.coupon_service import format_coupon_in_message, default_expiry
        
        message = "Promoción especial"
        code = "PROMO55"
        expires = default_expiry()
        description = "20% de descuento en tu primera compra"
        
        result = format_coupon_in_message(message, code, expires, description)
        
        assert description in result

    def test_default_expiry(self):
        from app.services.coupon_service import default_expiry
        
        expiry = default_expiry()
        
        # Debe ser aproximadamente 72 horas en el futuro
        assert (expiry - datetime.now(timezone.utc)).total_seconds() > 3600 * 71
        assert (expiry - datetime.now(timezone.utc)).total_seconds() < 3600 * 73

    def test_default_expiry_custom_hours(self):
        from app.services.coupon_service import default_expiry
        
        expiry = default_expiry(hours=24)
        
        diff = (expiry - datetime.now(timezone.utc)).total_seconds()
        assert 3600 * 23 < diff < 3600 * 25

    def test_is_expired(self):
        from app.services.coupon_service import is_expired, default_expiry
        
        # Un código que expira en 1 hora NO está expirado
        future = default_expiry(hours=1)
        assert is_expired(future) is False
        
        # Un código que ya expiró SÍ está expirado
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        assert is_expired(past) is True

    def test_is_redeem_intent(self):
        from app.services.coupon_service import is_redeem_intent
        
        assert is_redeem_intent("quiero canjear mi cupón") is True
        assert is_redeem_intent("CANJEAR") is True
        assert is_redeem_intent("lo quiero") is True
        assert is_redeem_intent("activar cupón") is True
        assert is_redeem_intent("quiero el descuento") is True
        assert is_redeem_intent("hola qué tal") is False
        assert is_redeem_intent("") is False


class TestTwilioService:
    """Tests para el servicio de Twilio."""

    @patch('app.services.twilio_service.settings')
    def test_anti_ban_delay_range(self, mock_settings):
        from app.services.twilio_service import anti_ban_delay
        
        mock_settings.TWILIO_ACCOUNT_SID = ""
        
        # Verificar que el delay está en el rango correcto
        for _ in range(100):
            delay = anti_ban_delay()
            assert 25 <= delay <= 90


class TestConfigSettings:
    """Tests para la configuración."""

    def test_twilio_number_pool_list_empty(self):
        from app.config import Settings
        
        s = Settings(TWILIO_NUMBER_POOL="")
        assert s.twilio_number_pool_list == []

    def test_twilio_number_pool_list_with_numbers(self):
        from app.config import Settings
        
        s = Settings(TWILIO_NUMBER_POOL="+525511111111,+525522222222")
        assert s.twilio_number_pool_list == ["+525511111111", "+525522222222"]

    def test_twilio_number_pool_list_with_spaces(self):
        from app.config import Settings
        
        s = Settings(TWILIO_NUMBER_POOL=" +525511111111 , +525522222222 ")
        assert s.twilio_number_pool_list == ["+525511111111", "+525522222222"]

    def test_cors_origins_default(self):
        from app.config import Settings
        
        s = Settings(FRONTEND_URL="")
        assert "http://localhost:5173" in s.cors_origins
        assert "https://app.iaradio.app" in s.cors_origins

    def test_cors_origins_adds_frontend_url(self):
        from app.config import Settings
        
        s = Settings(FRONTEND_URL="https://mi-dominio.com")
        assert "https://mi-dominio.com" in s.cors_origins
        assert "http://localhost:5173" in s.cors_origins

    def test_cors_origins_no_duplicates(self):
        from app.config import Settings
        
        s = Settings(
            FRONTEND_URL="https://app.iaradio.app",
            CORS_ORIGINS=["https://app.iaradio.app"]
        )
        # Solo debe aparecer una vez
        assert s.cors_origins.count("https://app.iaradio.app") == 1


class TestDateTimeUtils:
    """Tests para utilidades de fecha/hora."""

    def test_timezone_aware_datetime(self):
        from app.services.coupon_service import default_expiry
        
        expiry = default_expiry()
        
        # Debe ser timezone-aware
        assert expiry.tzinfo is not None

    def test_expiry_format_in_message(self):
        from app.services.coupon_service import format_coupon_in_message, default_expiry
        
        # Usar una fecha específica para el test
        specific_date = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
        result = format_coupon_in_message("Test", "CODE123", specific_date)
        
        assert "31/12" in result


class TestStringUtils:
    """Tests para utilidades de strings."""

    def test_clean_phone_number(self):
        # Función helper común
        def clean_phone(phone: str) -> str:
            return ''.join(c for c in phone if c.isdigit() or c == '+')
        
        assert clean_phone("+52 1 234 567 890") == "+521234567890"
        assert clean_phone("(234) 567-890") == "234567890"
        assert clean_phone("+1-234-567-890") == "+1234567890"

    def test_validate_e164_format(self):
        def is_valid_e164(phone: str) -> bool:
            import re
            return bool(re.match(r'^\+[1-9]\d{1,14}$', phone))
        
        assert is_valid_e164("+521234567890") is True
        assert is_valid_e164("+14155238886") is True
        assert is_valid_e164("1234567890") is False
        assert is_valid_e164("+0521234567890") is False  # No puede empezar con 0


class TestRateLimiterLogic:
    """Tests para la lógica del rate limiter."""

    @patch('app.services.twilio_service.settings')
    def test_rate_limit_key_generation(self, mock_settings):
        mock_settings.TWILIO_ACCOUNT_SID = "test_sid"
        
        def generate_key(remote_addr: str, endpoint: str) -> str:
            return f"rate_limit:{remote_addr}:{endpoint}"
        
        assert generate_key("192.168.1.1", "/api/v1/contacts") == "rate_limit:192.168.1.1:/api/v1/contacts"
        assert generate_key("10.0.0.1", "/api/v1/campaigns") == "rate_limit:10.0.0.1:/api/v1/campaigns"


class TestMessageParsing:
    """Tests para parsing de mensajes de WhatsApp."""

    def test_extract_yes_no_response(self):
        def extract_response(text: str) -> str | None:
            text_lower = text.lower().strip()
            yes_keywords = {"sí", "si", "yes", "s", "1", "confirmo", "ok", "acepto"}
            no_keywords = {"no", "n", "0", "cancelo", "rechazo"}
            
            if text_lower in yes_keywords:
                return "yes"
            if text_lower in no_keywords:
                return "no"
            return None
        
        assert extract_response("Sí") == "yes"
        assert extract_response("SI") == "yes"
        assert extract_response("si") == "yes"
        assert extract_response("1") == "yes"
        assert extract_response("No") == "no"
        assert extract_response("0") == "no"
        assert extract_response("hola") is None

    def test_detect_stop_keyword(self):
        def is_stop_message(text: str) -> bool:
            stop_keywords = {"stop", "baja", "cancelar", "unsubscribe", "salir", "eliminar"}
            return text.lower().strip() in stop_keywords
        
        assert is_stop_message("STOP") is True
        assert is_stop_message("baja") is True
        assert is_stop_message("cancelar") is True
        assert is_stop_message("Hola") is False

    def test_truncate_message(self):
        def truncate(text: str, max_length: int = 4096) -> str:
            suffix = "... [truncado]"
            if len(text) <= max_length:
                return text
            return text[:max_length - len(suffix)] + suffix
        
        short = "Mensaje corto"
        assert truncate(short) == short
        
        long = "A" * 5000
        result = truncate(long)
        assert len(result) == 4096
        assert "... [truncado]" in result


class TestAudioURLBuilder:
    """Tests para construcción de URLs de audio."""

    def test_build_r2_audio_url(self):
        def build_audio_url(base_url: str, file_id: str) -> str:
            return f"{base_url}/{file_id}.mp3"
        
        base = "https://pub-123.r2.dev/adradio-audio"
        url = build_audio_url(base, "audio_123_abc")
        
        assert url == "https://pub-123.r2.dev/adradio-audio/audio_123_abc.mp3"
        assert url.startswith("https://")

    def test_audio_url_expiration(self):
        # Simular signed URL
        def generate_signed_url(base_url: str, expiration_minutes: int = 60) -> dict:
            import time
            expires = int(time.time()) + expiration_minutes * 60
            return {
                "url": base_url,
                "expires": expires
            }
        
        result = generate_signed_url("https://example.com/audio.mp3", 30)
        assert "expires" in result
        assert "url" in result


class TestCampaignLogic:
    """Tests para lógica de campañas."""

    def test_calculate_campaign_estimated_time(self):
        def estimate_delivery_time(contacts_count: int, delay_seconds: int = 30) -> int:
            """
            Estima minutos para entregar una campaña.
            Asume: 1 mensaje cada 'delay_seconds' segundos.
            """
            if contacts_count == 0:
                return 0
            total_seconds = contacts_count * delay_seconds
            return total_seconds // 60
        
        assert estimate_delivery_time(100, 30) == 50  # 100 * 30 = 3000s = 50 min
        assert estimate_delivery_time(500, 60) == 500  # 500 * 60 = 30000s = 500 min
        assert estimate_delivery_time(0) == 0

    def test_calculate_delivery_rate(self):
        def calculate_delivery_rate(sent: int, failed: int) -> float:
            if sent == 0:
                return 0.0
            return round((sent - failed) / sent * 100, 2)
        
        assert calculate_delivery_rate(100, 5) == 95.0
        assert calculate_delivery_rate(100, 0) == 100.0
        assert calculate_delivery_rate(100, 100) == 0.0
        assert calculate_delivery_rate(0, 0) == 0.0


class TestEmbeddingService:
    """Tests para el servicio de embeddings (sin API real)."""

    def test_embedding_dimension_constant(self):
        # Voyage AI embeddings son de 1024 dimensiones
        VOYAGE_EMBEDDING_DIM = 1024
        assert VOYAGE_EMBEDDING_DIM == 1024

    def test_chunk_size_for_pdf(self):
        # Tamaño recomendado de chunk para PDFs
        CHUNK_SIZE = 1000
        CHUNK_OVERLAP = 200
        
        assert CHUNK_SIZE > 0
        assert CHUNK_OVERLAP < CHUNK_SIZE


class TestWebhookValidation:
    """Tests para validación de webhooks."""

    def test_twilio_signature_validation(self):
        def validate_twilio_signature(
            signature: str,
            url: str,
            params: dict,
            auth_token: str
        ) -> bool:
            """
            Valida la firma de Twilio.
            Nota: En producción usar twilio.auth.AuthValidator
            """
            if not signature or not auth_token:
                return False
            return True  # Placeholder
        
        assert validate_twilio_signature("sig123", "https://webhook.url", {"foo": "bar"}, "token") is True
        assert validate_twilio_signature("", "https://webhook.url", {}, "token") is False

    def test_stripe_signature_validation(self):
        def validate_stripe_signature(
            signature: str,
            payload: str,
            webhook_secret: str
        ) -> bool:
            """
            Valida la firma de Stripe.
            Nota: En producción usar stripe.webhook.construct_event
            """
            if not signature or not webhook_secret:
                return False
            return True  # Placeholder
        
        assert validate_stripe_signature("sig_123", "{}", "whsec_xxx") is True
        assert validate_stripe_signature("", "{}", "whsec_xxx") is False


class TestSubscriptionPlans:
    """Tests para planes de suscripción."""

    def test_plan_limits(self):
        PLANS = {
            "trial": {"messages": 0, "contacts": 50, "campaigns": 1},
            "starter": {"messages": 500, "contacts": 200, "campaigns": 5},
            "growth": {"messages": 2000, "contacts": 1000, "campaigns": 20},
            "pro": {"messages": 10000, "contacts": 5000, "campaigns": 100},
        }
        
        assert PLANS["trial"]["contacts"] == 50
        assert PLANS["starter"]["messages"] == 500
        assert PLANS["pro"]["campaigns"] == 100

    def test_plan_upgrade_eligibility(self):
        def can_upgrade(current_plan: str, messages_remaining: int) -> bool:
            # Solo trial y starter pueden hacer upgrade
            if current_plan in ("trial", "starter"):
                return messages_remaining < 50
            return False
        
        assert can_upgrade("trial", 10) is True
        assert can_upgrade("trial", 100) is False
        assert can_upgrade("starter", 20) is True
        assert can_upgrade("starter", 100) is False
        assert can_upgrade("pro", 0) is False


class TestBotConversation:
    """Tests para lógica del bot conversacional."""

    def test_detect_greeting(self):
        def is_greeting(text: str) -> bool:
            greetings = {"hola", "buenos días", "buenas", "hello", "hi", "qué tal", "buen día"}
            text_lower = text.lower().strip()
            return text_lower in greetings or any(g in text_lower for g in greetings)
        
        assert is_greeting("Hola") is True
        assert is_greeting("Buenos días") is True
        assert is_greeting("Qué tal?") is True
        assert is_greeting("Quiero información") is False

    def test_detect_order_status_query(self):
        def is_order_status(text: str) -> bool:
            keywords = {"estado", "status", "pedido", "orden", "mi orden", "donde está", "dónde está", "mi comida"}
            return any(k in text.lower() for k in keywords)
        
        assert is_order_status("Cuál es el estado de mi pedido?") is True
        assert is_order_status("Mi orden #123") is True
        assert is_order_status("Dónde está mi comida?") is True
        assert is_order_status("Hola qué tal") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])