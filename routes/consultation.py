from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.session_store import create_session, add_message, get_message
from core.intake_ai import mock_llm_reply, mock_summary

router = APIRouter(prefix="/consultation", tags=["consultation"])


class StartResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


class SummaryRequest(BaseModel):
    session_id: str


@router.post("/start", response_model=StartResponse)
def start_consultation():
    session_id = create_session()
    return {"session_id": session_id}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        add_message(req.session_id, "user", req.message)

        reply = mock_llm_reply(req.message)

        add_message(req.session_id, "assistant", reply)

        return {"reply": reply}
    except:
        raise HTTPException(status_code=404, detail="Invalid session")


@router.post("/summary")
def summarize(req: SummaryRequest):
    try:
        messages = get_message(req.session_id)
        return mock_summary(messages)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid session")
