"""
Redis-backed store for the multi-step doctor registration flow.

Nothing about a doctor is written to Postgres until `finalize` succeeds —
this store is the *only* place the in-progress registration lives across the
3 steps (start -> verify-identity -> finalize). This avoids ever persisting
half-finished / unverified doctor rows (unverified PII, orphaned "pending"
users that never complete signup, username/email squatting, etc).

If verification is rejected too many times, or the TTL expires, the whole
registration is discarded and the doctor must start over from `start`.
"""
import json
import secrets
import uuid
from datetime import datetime

from core.redis_client import redis_client

REGISTRATION_TTL_SECONDS = 45 * 60  # 45 minutes to complete all 3 steps
REGISTRATION_TTL_MINUTES = REGISTRATION_TTL_SECONDS // 60

# How many times identity verification may be *declined* before we force the
# doctor to restart registration from scratch. Errors from VerifyNow itself
# (service unavailable) do NOT count against this - only genuine mismatches.
MAX_VERIFICATION_ATTEMPTS = 3


def _key(registration_id: str) -> str:
    return f"doctor_registration:{registration_id}"


def create_registration(username: str, email: str, hashed_password: str) -> str:
    registration_id = uuid.uuid4().hex + secrets.token_urlsafe(8)

    data = {
        "username": username,
        "email": email,
        "hashed_password": hashed_password,
        "status": "profile_submitted",  # profile_submitted -> verified -> finalized
        "verification_attempts": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    redis_client.setex(_key(registration_id), REGISTRATION_TTL_SECONDS, json.dumps(data))
    return registration_id


def get_registration(registration_id: str) -> dict | None:
    raw = redis_client.get(_key(registration_id))
    if not raw:
        return None
    return json.loads(raw)


def update_registration(registration_id: str, **fields) -> dict:
    """Merge `fields` into the stored registration and refresh its TTL."""
    data = get_registration(registration_id)
    if data is None:
        raise ValueError("Registration not found or has expired")

    data.update(fields)
    data["updated_at"] = datetime.now().isoformat()

    redis_client.setex(_key(registration_id), REGISTRATION_TTL_SECONDS, json.dumps(data))
    return data


def delete_registration(registration_id: str) -> None:
    redis_client.delete(_key(registration_id))
