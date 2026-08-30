"""
Symmetric Credential Encryption Service for DoxaRank.

Provides authenticated AES-128 (CBC mode + HMAC-SHA256) encryption at rest using
cryptography.fernet.Fernet for sensitive OAuth2 refresh tokens and API secrets.
Never exposes plaintext tokens in the database or logs.
"""

import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """
    Deterministically derive a 32-byte URL-safe base64 encryption key.
    Prefers GSC_TOKEN_ENCRYPTION_KEY if configured; falls back to SECRET_KEY.
    """
    configured_key = getattr(settings, 'GSC_TOKEN_ENCRYPTION_KEY', None)
    if configured_key and isinstance(configured_key, str) and configured_key.strip():
        raw_key = configured_key.strip()
    else:
        raw_key = getattr(settings, 'SECRET_KEY', 'doxarank-default-insecure-key')

    # Hash to 32 bytes and urlsafe-b64encode for Fernet compatibility
    sha = hashlib.sha256(raw_key.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(sha)


def get_fernet_cipher() -> Fernet:
    """Return a configured Fernet cipher instance."""
    return Fernet(_get_encryption_key())


def encrypt_token(raw_token: Optional[str]) -> Optional[str]:
    """
    Encrypt a plaintext token string into a safe base64 ciphertext string.
    Returns None if raw_token is empty or None.
    """
    if not raw_token:
        return None

    try:
        cipher = get_fernet_cipher()
        encrypted_bytes = cipher.encrypt(raw_token.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as exc:
        logger.error(f"[EncryptionService] Failed to encrypt token: {exc}")
        raise


def decrypt_token(encrypted_token: Optional[str]) -> Optional[str]:
    """
    Decrypt a ciphertext string back into the plaintext token string.
    Returns None if encrypted_token is empty or None.
    """
    if not encrypted_token:
        return None

    try:
        cipher = get_fernet_cipher()
        decrypted_bytes = cipher.decrypt(encrypted_token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        logger.error("[EncryptionService] Invalid encryption token or key mismatch during decryption.")
        return None
    except Exception as exc:
        logger.error(f"[EncryptionService] Failed to decrypt token: {exc}")
        return None
