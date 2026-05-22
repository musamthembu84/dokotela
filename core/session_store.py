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


def get_message(session_id: str):
    raw = redis_client.get(_key(session_id))

    if not raw:
        raise ValueError("Invalid session")

    data = json.loads(raw.decode("utf-8"))
    return data["messages"]


def get_session(session_id: str) -> dict | None:
    """Return the full session dict, or None if it doesn't exist / has expired."""
    raw = redis_client.get(_key(session_id))
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))

