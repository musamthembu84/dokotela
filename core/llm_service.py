"""
Remote LLM inference service for Dokotela.

MedGemma runs on a separate GPU inference service.
FastAPI communicates with that service through an
OpenAI-compatible /v1/chat/completions API.
"""

import json
import logging
import re

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


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

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(
                url,
                headers=headers,
                json=payload,
            )

        response.raise_for_status()

    except httpx.TimeoutException:
        logger.exception("LLM inference request timed out")
        raise

    except httpx.HTTPStatusError as exc:
        logger.error(
            "LLM inference service returned HTTP %s: %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise

    except httpx.RequestError:
        logger.exception(
            "Could not connect to LLM inference service"
        )
        raise

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
