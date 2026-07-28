"""
AES-256-GCM encryption for secrets at rest (Meta WhatsApp tokens).

Port of vocero-crm's src/lib/crypto/index.ts. Same on-disk shape (3 base64
columns: cipher, iv, tag) so the pattern is directly comparable, but Python's
AESGCM returns ciphertext+tag concatenated (unlike Node, which exposes the
tag separately via getAuthTag()) — encrypt_secret splits the last 16 bytes
off as the tag before storing, decrypt_secret reassembles them.
"""
import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_LEN = 12
_TAG_LEN = 16


class CryptoError(Exception):
    """A secret failed to decrypt (wrong/rotated key, corrupted value, etc.)."""


@dataclass
class EncryptedValue:
    cipher: str  # base64
    iv: str  # base64
    tag: str  # base64


def _get_key() -> bytes:
    """Decode ENCRYPTION_KEY fresh on every call — never cache it, so a key
    rotation can't leave a stale wrong-length key in memory."""
    raw = settings.ENCRYPTION_KEY
    if not raw:
        raise CryptoError("ENCRYPTION_KEY no está configurada")
    try:
        key = base64.b64decode(raw)
    except Exception as e:
        raise CryptoError("ENCRYPTION_KEY no es base64 válido") from e
    if len(key) != 32:
        raise CryptoError("ENCRYPTION_KEY debe ser exactamente 32 bytes en base64 (44 caracteres)")
    return key


def encrypt_secret(plain: str) -> EncryptedValue:
    nonce = os.urandom(_NONCE_LEN)
    combined = AESGCM(_get_key()).encrypt(nonce, plain.encode("utf-8"), None)
    ciphertext, tag = combined[:-_TAG_LEN], combined[-_TAG_LEN:]
    return EncryptedValue(
        cipher=base64.b64encode(ciphertext).decode(),
        iv=base64.b64encode(nonce).decode(),
        tag=base64.b64encode(tag).decode(),
    )


def decrypt_secret(value: EncryptedValue) -> str:
    try:
        nonce = base64.b64decode(value.iv)
        ciphertext = base64.b64decode(value.cipher)
        tag = base64.b64decode(value.tag)
        plain = AESGCM(_get_key()).decrypt(nonce, ciphertext + tag, None)
        return plain.decode("utf-8")
    except InvalidTag as e:
        raise CryptoError("El secreto no descifró — clave rotada o valor corrupto") from e
    except CryptoError:
        raise
    except Exception as e:
        raise CryptoError(f"Error descifrando secreto: {e}") from e
