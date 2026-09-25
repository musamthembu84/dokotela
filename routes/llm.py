import logging

from fastapi import APIRouter
from pydantic import BaseModel

from core.llm_service import LLMWarmingUpError, generate_llm_reply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])

# Small, disposable prompt used only to wake up the RunPod worker /
# MedGemma model. Its response is discarded - this is never shown to
# the user and never part of a real consultation.
WARMUP_PROMPT = "I feel sick today"

# Keep the generated output as short as possible: we only care that the
# worker loads and responds, not about the content of the reply.
WARMUP_MAX_TOKENS = 8


class WarmupResponse(BaseModel):
    status: str


@router.post("/warmup", response_model=WarmupResponse)
def warmup_llm():
    """
    Fire a minimal, real inference request at the existing LLM service so
    the RunPod worker / MedGemma model starts loading ahead of time.

    Intended to be called once when the homepage loads, in the
    background. The response is a simple status only - the generated
    text is intentionally discarded and never surfaced to the user.

    This must never break the caller: any failure (including a cold
    start timeout) is swallowed and reported as a non-fatal status
    instead of raising, since a failed warm-up must not affect the
    homepage or the real consultation flow.
    """

    try:
        generate_llm_reply(
            [{"role": "user", "content": WARMUP_PROMPT}],
            max_tokens=WARMUP_MAX_TOKENS,
        )

        return {"status": "warmed"}

    except LLMWarmingUpError:
        # Expected outcome on a genuine cold start - the worker is now
        # starting, which is exactly the point of the warm-up call.
        logger.info("LLM warm-up triggered a cold start")

        return {"status": "warming"}

    except Exception:
        # Never let a warm-up failure surface as an error to the caller.
        logger.exception("LLM warm-up request failed")

        return {"status": "failed"}
