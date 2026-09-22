from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.session_store import create_session, add_message, get_message, get_session
from core.llm_service import (
    generate_llm_reply,
    generate_llm_summary,
    clean_llm_text,
    is_termination_message,
    LLMWarmingUpError,
)

router = APIRouter(prefix="/consultation", tags=["consultation"])


class StartResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    ended: bool = False
    summary: dict | None = None


class SummaryRequest(BaseModel):
    session_id: str


class SessionMessage(BaseModel):
    role: str
    content: str
    ts: str


class SessionResponse(BaseModel):
    session_id: str
    messages: list[SessionMessage]


@router.post("/start", response_model=StartResponse)
def start_consultation():
    session_id = create_session()
    return {"session_id": session_id}


@router.get("/session/{session_id}", response_model=SessionResponse)
def get_consultation_session(session_id: str):
    """
    Return the full stored history for a session. Used by the frontend
    to rehydrate a chat that lost its in-memory state (e.g. a hard
    refresh, or the very first request to a session having timed out
    client-side while it was still being processed on the backend).
    """
    session = get_session(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Invalid session")

    return {"session_id": session_id, "messages": session["messages"]}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        add_message(req.session_id, "user", req.message)

        if is_termination_message(req.message):
            history = get_message(req.session_id)
            summary = generate_llm_summary(history)

            reply = (
                "Thanks for sharing that. I have what I need for now — a "
                "doctor will review this summary and call you shortly."
            )
            add_message(req.session_id, "assistant", reply)

            return {"reply": reply, "ended": True, "summary": summary}

        history = get_message(req.session_id)
        reply = clean_llm_text(generate_llm_reply(history))

        add_message(req.session_id, "assistant", reply)

        return {"reply": reply}
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid session")
    except LLMWarmingUpError as exc:
        # 503 (not 500) so the frontend can tell this apart from a real
        # failure and show a "still warming up" message with a retry,
        # instead of a generic "couldn't process that" error.
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/summary")
def summarize(req: SummaryRequest):
    try:
        messages = get_message(req.session_id)
        return generate_llm_summary(messages)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid session")

