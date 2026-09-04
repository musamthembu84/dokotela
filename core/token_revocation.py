"""
Redis-backed JWT revocation ("blacklist") store.

Access tokens are stateless by design, so signing a user out requires
recording that a specific token (identified by its `jti` claim) must no
longer be accepted, until it would have expired naturally anyway.

Each revoked entry is stored with a TTL equal to the token's remaining
lifetime, so the blacklist never grows unbounded - Redis expires the key
automatically once the token would have expired regardless.
"""
from datetime import datetime, timezone

from core.redis_client import redis_client

_KEY_PREFIX = "revoked_token:"


def _key(jti: str) -> str:
    return f"{_KEY_PREFIX}{jti}"


def revoke_token(jti: str, expires_at: datetime) -> None:
    """Mark a token's jti as revoked until its natural expiry time."""
    ttl_seconds = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    if ttl_seconds <= 0:
        # Token already expired naturally - nothing to do.
        return
    redis_client.setex(_key(jti), ttl_seconds, "1")


def is_token_revoked(jti: str) -> bool:
    if not jti:
        return False
    return redis_client.exists(_key(jti)) == 1
