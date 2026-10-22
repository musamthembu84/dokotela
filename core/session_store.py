import json
import uuid
from datetime import datetime

from core.redis_client import redis_client

SESSION_TTL_SECONDS = 60 * 30


def _key(session_id: str) -> str:
    return f"consultation:{session_id}"


def create_session() -> str:
    session_id = str(uuid.uuid4())

    data = {
        "messages": [],
        "created_at": datetime.now().isoformat()
    }

    redis_client.setex(_key(session_id), SESSION_TTL_SECONDS, json.dumps(data))
    return session_id


def add_message(session_id: str, role: str, content: str):
    raw = redis_client.get(_key(session_id))

    if not raw:
        raise ValueError("Invalid session")

    data = json.loads(raw)

    data["messages"].append(
        {
            "role": role,
            "content": content,
            "ts": datetime.now().isoformat()
        }
    )

    redis_client.setex(_key(session_id), SESSION_TTL_SECONDS, json.dumps(data))


def remove_last_message(session_id: str):
    """
    Remove the most recently added message, if any. Used to roll back a
    user's turn when generating the assistant's reply fails, so a failed
    request doesn't leave two consecutive same-role turns in history -
    MedGemma's chat template strictly enforces user/assistant alternation
    and permanently fails every later request in the session (not just
    the failed one) once that happens.
    """
    raw = redis_client.get(_key(session_id))

    if not raw:
        return

    data = json.loads(raw)

    if data["messages"]:
        data["messages"].pop()

    redis_client.setex(_key(session_id), SESSION_TTL_SECONDS, json.dumps(data))


def get_message(session_id: str):
    raw = redis_client.get(_key(session_id))

    if not raw:
        raise ValueError("Invalid session")

    data = json.loads(raw.decode("utf-8"))
    return data["messages"]


def set_summary(session_id: str, summary: str):
    """Attach the AI-generated SOAP summary to the session, generated at
    checkout time so it's ready well before the payment webhook needs it."""
    raw = redis_client.get(_key(session_id))

    if not raw:
        return

    data = json.loads(raw)
    data["summary"] = summary

    redis_client.setex(_key(session_id), SESSION_TTL_SECONDS, json.dumps(data))


def get_session(session_id: str) -> dict | None:
    """Return the full session dict, or None if it doesn't exist / has expired."""
    raw = redis_client.get(_key(session_id))
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))

