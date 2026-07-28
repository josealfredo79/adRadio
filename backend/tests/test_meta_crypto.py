"""Tests for app.core.crypto (AES-256-GCM secret encryption at rest)."""
import base64
from unittest.mock import patch

import pytest

from app.core.crypto import CryptoError, EncryptedValue, decrypt_secret, encrypt_secret

VALID_KEY = base64.b64encode(b"0" * 32).decode()


@pytest.fixture(autouse=True)
def _encryption_key():
    with patch("app.core.crypto.settings") as mock_settings:
        mock_settings.ENCRYPTION_KEY = VALID_KEY
        yield mock_settings


class TestRoundTrip:
    def test_encrypt_decrypt_roundtrip(self):
        secret = "EAAGabc123fake-meta-token"
        enc = encrypt_secret(secret)
        assert decrypt_secret(enc) == secret

    def test_ciphertext_differs_from_plaintext(self):
        enc = encrypt_secret("hello")
        assert enc.cipher != "hello"

    def test_nonce_is_random_per_call(self):
        enc1 = encrypt_secret("same-secret")
        enc2 = encrypt_secret("same-secret")
        assert enc1.iv != enc2.iv
        assert enc1.cipher != enc2.cipher  # different nonce -> different ciphertext

    def test_empty_string_roundtrip(self):
        enc = encrypt_secret("")
        assert decrypt_secret(enc) == ""

    def test_unicode_roundtrip(self):
        secret = "tökén-with-ñ-and-emoji-🔒"
        enc = encrypt_secret(secret)
        assert decrypt_secret(enc) == secret


class TestTamperDetection:
    def test_tampered_tag_raises(self):
        enc = encrypt_secret("secret-value")
        tampered = EncryptedValue(cipher=enc.cipher, iv=enc.iv, tag=base64.b64encode(b"x" * 16).decode())
        with pytest.raises(CryptoError):
            decrypt_secret(tampered)

    def test_tampered_ciphertext_raises(self):
        enc = encrypt_secret("secret-value")
        raw = bytearray(base64.b64decode(enc.cipher))
        raw[0] ^= 0xFF
        tampered = EncryptedValue(cipher=base64.b64encode(bytes(raw)).decode(), iv=enc.iv, tag=enc.tag)
        with pytest.raises(CryptoError):
            decrypt_secret(tampered)

    def test_wrong_key_raises(self):
        enc = encrypt_secret("secret-value")
        other_key = base64.b64encode(b"1" * 32).decode()
        with patch("app.core.crypto.settings") as mock_settings:
            mock_settings.ENCRYPTION_KEY = other_key
            with pytest.raises(CryptoError):
                decrypt_secret(enc)


class TestKeyValidation:
    def test_missing_key_raises(self):
        with patch("app.core.crypto.settings") as mock_settings:
            mock_settings.ENCRYPTION_KEY = ""
            with pytest.raises(CryptoError):
                encrypt_secret("x")

    def test_wrong_length_key_raises(self):
        short_key = base64.b64encode(b"short").decode()
        with patch("app.core.crypto.settings") as mock_settings:
            mock_settings.ENCRYPTION_KEY = short_key
            with pytest.raises(CryptoError):
                encrypt_secret("x")

    def test_non_base64_key_raises(self):
        with patch("app.core.crypto.settings") as mock_settings:
            mock_settings.ENCRYPTION_KEY = "not-valid-base64!!!@#$"
            with pytest.raises(CryptoError):
                encrypt_secret("x")
