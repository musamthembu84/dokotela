"""
Redis-backed refresh token store implementing an idle-timeout session model.

Design:
- Access tokens (JWT) stay short-lived (see ACCESS_TOKEN_EXPIRE_MINUTES) and
  are never stored server-side.
- A refresh token is a random opaque string mapped to the user's identity in
  Redis, with a TTL of REFRESH_TOKEN_EXPIRE_MINUTES. Every successful use of
  the refresh token slides that TTL forward, so an *active* user is
  effectively never logged out - only a genuinely idle user (no requests for
  REFRESH_TOKEN_EXPIRE_MINUTES) gets kicked out.
- An absolute "created_at" timestamp is stored alongside the token so we can
  enforce a hard cap (REFRESH_TOKEN_ABSOLUTE_EXPIRE_HOURS) on total session
  length, regardless of activity - defense in depth if a refresh token were
  ever stolen.
- Refresh tokens are rotated on every use (old one deleted, new one issued)
  to limit the blast radius of a leaked token and to detect reuse.

Redis footprint: one small key per currently active (non-idle) session,
auto-expiring - bounded by concurrent active users, not total registered
users.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone

from core.config import settings
from core.redis_client import redis_client

_KEY_PREFIX = "refresh_token:"


def _key(token: str) -> str:
    return f"{_KEY_PREFIX}{token}"


def _ttl_seconds() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60


def issue_refresh_token(user_id: int, created_at: datetime | None = None) -> str:
    """Create a brand-new refresh token for the given user and store it."""
    token = secrets.token_urlsafe(48)
    data = {
        "user_id": user_id,
        "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
    }
    redis_client.setex(_key(token), _ttl_seconds(), json.dumps(data))
    return token


def rotate_refresh_token(token: str) -> tuple[str, int] | None:
    """
    Validate `token`, then atomically replace it with a new one (sliding the
    idle-timeout window forward), preserving the original `created_at` so
    the absolute session cap is enforced correctly.

    Returns (new_token, user_id) or None if the token is invalid/expired/
    past the absolute session cap.
    """
    raw = redis_client.get(_key(token))
    if not raw:
        return None

    data = json.loads(raw)
    created_at = datetime.fromisoformat(data["created_at"])
    absolute_cap = timedelta(hours=settings.REFRESH_TOKEN_ABSOLUTE_EXPIRE_HOURS)

    # Always invalidate the old token first (rotation) - single use only.
    redis_client.delete(_key(token))

    if datetime.now(timezone.utc) - created_at > absolute_cap:
        return None

    new_token = secrets.token_urlsafe(48)
    redis_client.setex(
        _key(new_token),
        _ttl_seconds(),
        json.dumps({"user_id": data["user_id"], "created_at": data["created_at"]}),
    )
    return new_token, data["user_id"]


def revoke_refresh_token(token: str) -> None:
    """Invalidate a refresh token immediately (e.g. on sign-out)."""
    redis_client.delete(_key(token))
