"""
Remote LLM inference service for Dokotela.

MedGemma runs on a separate GPU inference service.
FastAPI communicates with that service through an
OpenAI-compatible /v1/chat/completions API.
"""

import json
import logging
import re
import time

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# RunPod bills for GPU worker time, and a timeout after this long usually
# means a job is genuinely still running/cold-starting on a paid worker -
# retrying it would risk starting a second billed worker on top of the
# first. So we only retry cheap, instant failures (a dropped connection,
# or an immediate 5xx from the queue before any worker was billed); a
# real timeout is raised straight away instead of being retried.
LLM_MAX_ATTEMPTS = 2
LLM_RETRY_BACKOFF_SECONDS = 2.0


class LLMWarmingUpError(RuntimeError):
    """
    Raised when the remote LLM inference service could not be reached in
    time, most likely because the RunPod worker is still cold-starting.
    Callers can use this to show a friendly "still warming up, please
    try again shortly" message instead of a generic failure.
    """


SYSTEM_PROMPT = (
    "You are Dokotela, an AI medical intake assistant. Your ONLY purpose is "
    "to collect information about a patient's health concern: symptoms, "
    "duration, severity and history. You are not a doctor: never give a "
    "diagnosis or prescribe treatment. If the patient describes symptoms that "
    "could be a medical emergency (e.g. difficulty breathing, chest pain, "
    "severe bleeding, stroke symptoms, loss of consciousness), immediately "
    "tell them to click button below and schedule call with a doctor. "
    "If the patient's message is NOT related to a health or medical concern "
    "(e.g. small talk, hobbies, unrelated questions), do NOT answer it or "
    "engage with the topic. Instead, politely say you can only help with "
    "medical/health concerns, and ask them to describe what health issue "
    "they'd like help with today. "
    "Reply in plain conversational text only: no markdown, no asterisks, no "
    "headings, no bullet symbols, no backticks."
)


SUMMARY_INSTRUCTION = (
    "Based on the conversation so far, respond with ONLY a JSON object "
    "(no extra text, no markdown) with exactly these keys: "
    '"chief_complaint" (short string), '
    '"risk_level" (one of "low", "medium", "high", "emergency"), '
    '"recommended_speciality" (string), '
    '"summary" (a short clinical summary of the conversation).'
)


def generate_llm_reply(
    messages: list[dict],
    max_tokens: int = 256,
) -> str:
    """
    Send a chat request to the remote MedGemma inference service.

    The remote service must expose an OpenAI-compatible endpoint:
        POST /v1/chat/completions
    """

    chat_messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    chat_messages.extend(
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in messages
    )

    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }

    url = f"{settings.LLM_SERVICE_URL.rstrip('/')}/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.RUNPOD_API_KEY}",
        "Content-Type": "application/json",
    }

    logger.info(
        "Sending LLM request to remote inference service: %s",
        url,
    )

    logger.info(
        "LLM request: messages=%d, chars=%d, max_tokens=%d",
        len(chat_messages),
        sum(len(m["content"]) for m in chat_messages),
        max_tokens,
    )

    # RunPod serverless workers scale to zero when idle, so the first
    # request after a period of inactivity has to wait for a cold start
    # (observed: 3-5 minutes) before inference even begins. A short
    # read timeout here would abandon the request mid cold-start, so we
    # give it a generous ceiling (comfortably under the reverse proxy's
    # own proxy_read_timeout) while keeping connect/write timeouts tight
    # so genuine connectivity failures still fail fast.
    timeout = httpx.Timeout(connect=10.0, write=10.0, pool=10.0, read=280.0)

    last_exc: Exception | None = None

    for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

            response.raise_for_status()
            last_exc = None
            break

        except httpx.TimeoutException as exc:
            # A timeout this long almost certainly means a worker was
            # already spun up and is mid cold-start/inference (i.e.
            # already being billed). Retrying here would risk paying for
            # a second worker on top of the first, so we fail fast
            # instead of looping.
            logger.warning(
                "LLM inference request timed out after %.0fs read timeout "
                "- not retrying (a worker is likely already billed and "
                "still starting up)",
                timeout.read,
            )
            raise LLMWarmingUpError(
                "The AI service is still starting up. Please try again "
                "in a moment."
            ) from exc

        except httpx.HTTPStatusError as exc:
            last_exc = exc
            logger.error(
                "LLM inference service returned HTTP %s (attempt %d/%d): %s",
                exc.response.status_code,
                attempt,
                LLM_MAX_ATTEMPTS,
                exc.response.text,
            )
            # Only worth retrying on transient/queueing errors, not on
            # client errors like a bad payload or bad auth.
            if exc.response.status_code < 500:
                raise

        except httpx.RequestError as exc:
            # A connection-level failure (refused, DNS, etc.) happens
            # before any worker is billed, so it's cheap/safe to retry.
            last_exc = exc
            logger.warning(
                "Could not connect to LLM inference service (attempt %d/%d)",
                attempt,
                LLM_MAX_ATTEMPTS,
            )

        if last_exc is not None and attempt < LLM_MAX_ATTEMPTS:
            time.sleep(LLM_RETRY_BACKOFF_SECONDS * attempt)

    if last_exc is not None:
        logger.exception(
            "LLM inference request failed after %d attempt(s)",
            LLM_MAX_ATTEMPTS,
            exc_info=last_exc,
        )

        if isinstance(last_exc, httpx.RequestError):
            raise LLMWarmingUpError(
                "The AI service is still starting up. Please try again "
                "in a moment."
            ) from last_exc

        raise last_exc

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error(
            "Unexpected LLM response format: %s",
            data,
        )
        raise RuntimeError(
            "Invalid response received from LLM inference service"
        ) from exc

    return content.strip()


def _format_transcript(messages: list[dict]) -> str:
    speaker_labels = {
        "user": "Patient",
        "assistant": "Assistant",
    }

    lines = [
        f"{speaker_labels.get(message['role'], message['role'])}: "
        f"{message['content']}"
        for message in messages
    ]

    return "\n".join(lines)


def generate_llm_summary(
    messages: list[dict],
    max_tokens: int = 300,
) -> dict:
    """
    Generate a structured clinical summary from the consultation history.
    """

    transcript = _format_transcript(messages)

    instruction = (
        f"{SUMMARY_INSTRUCTION}\n\n"
        f"Conversation:\n{transcript}"
    )

    raw = generate_llm_reply(
        [
            {
                "role": "user",
                "content": instruction,
            }
        ],
        max_tokens=max_tokens,
    )

    match = re.search(r"\{.*\}", raw, re.DOTALL)

    json_text = match.group(0) if match else raw

    try:
        data = json.loads(json_text)

    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse LLM summary as JSON. "
            "Falling back to raw text: %s",
            raw,
        )

        data = {
            "chief_complaint": "",
            "risk_level": "medium",
            "recommended_speciality": "general_practice",
            "summary": raw[:300],
        }

    return data


TERMINATION_PHRASES = (
    "schedule a call",
    "schedule call",
    "book a call",
    "speak to a doctor",
    "talk to a doctor",
)


def is_termination_message(message: str) -> bool:
    """
    True if the patient's message signals they want to end
    the intake chat.
    """

    lowered = message.lower()

    return any(
        phrase in lowered
        for phrase in TERMINATION_PHRASES
    )


_BOLD_ITALIC_RE = re.compile(
    r"\*\*(.*?)\*\*|\*(.*?)\*|__(.*?)__|_(.*?)_"
)

_HEADING_RE = re.compile(
    r"^#{1,6}\s*",
    re.MULTILINE,
)

_BULLET_RE = re.compile(
    r"^[ \t]*[\*\-•][ \t]+",
    re.MULTILINE,
)

_BACKTICK_RE = re.compile(
    r"`+"
)

_BLANK_LINES_RE = re.compile(
    r"\n{3,}"
)


def clean_llm_text(text: str) -> str:
    """
    Strip markdown formatting and normalize whitespace so
    replies are returned as clean plain text.
    """

    def _unwrap(match: re.Match) -> str:
        return next(
            group
            for group in match.groups()
            if group is not None
        )

    text = _BOLD_ITALIC_RE.sub(
        _unwrap,
        text,
    )

    text = _BACKTICK_RE.sub(
        "",
        text,
    )

    text = _HEADING_RE.sub(
        "",
        text,
    )

    text = _BULLET_RE.sub(
        "- ",
        text,
    )

    text = _BLANK_LINES_RE.sub(
        "\n\n",
        text,
    )

    return text.strip()
