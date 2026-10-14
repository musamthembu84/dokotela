"""
Field-level encryption for sensitive data at rest (currently: doctors'
payout bank account numbers). Uses Fernet (AES-128-CBC + HMAC), keyed by
PAYOUT_ENCRYPTION_KEY.

If PAYOUT_ENCRYPTION_KEY is ever rotated, existing encrypted values must be
decrypted with the old key and re-encrypted with the new one - this module
intentionally does not attempt multi-key decryption to keep it simple; add
that if/when key rotation is actually needed.
"""
from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

_fernet = Fernet(settings.PAYOUT_ENCRYPTION_KEY.encode())


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt value - wrong key or corrupted data") from exc
