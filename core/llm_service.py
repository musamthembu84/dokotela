"""
Local LLM inference service backed by mlx_lm.

Loads the configured model once (lazily, thread-safe) and reuses it for every
chat reply / consultation summary, instead of hardcoding responses.
"""
import json
import logging
import re
import threading

from core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_tokenizer = None

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


def load_llm():
    """Load (or return the already-loaded) model/tokenizer. Thread-safe."""
    global _model, _tokenizer

    if _model is None:
        with _lock:
            if _model is None:
                from mlx_lm import load

                logger.info("Loading LLM model: %s", settings.LLM_MODEL_NAME)
                _model, _tokenizer = load(settings.LLM_MODEL_NAME)
                logger.info("LLM model loaded")

    return _model, _tokenizer


def _build_prompt(messages: list[dict]) -> str:
    _, tokenizer = load_llm()

    chat = [{"role": "system", "content": SYSTEM_PROMPT}]
    chat += [{"role": m["role"], "content": m["content"]} for m in messages]

    if tokenizer.chat_template is not None:
        return tokenizer.apply_chat_template(chat, add_generation_prompt=True)

    return "\n".join(f"{m['role']}: {m['content']}" for m in chat)


def generate_llm_reply(messages: list[dict], max_tokens: int = 256) -> str:
    """
    messages: full conversation history,
    e.g. [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    from mlx_lm import generate

    model, tokenizer = load_llm()
    prompt = _build_prompt(messages)

    response = generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)
    return response.strip()


def _format_transcript(messages: list[dict]) -> str:
    speaker_labels = {"user": "Patient", "assistant": "Assistant"}
    lines = [f"{speaker_labels.get(m['role'], m['role'])}: {m['content']}" for m in messages]
    return "\n".join(lines)


def generate_llm_summary(messages: list[dict], max_tokens: int = 300) -> dict:
    # Flatten the conversation into a transcript and ask in a single fresh
    # user turn, rather than appending another "user" role onto the existing
    # history (which can break strict user/assistant alternation required by
    # some chat templates, e.g. if the last history message was also "user").
    transcript = _format_transcript(messages)
    instruction = f"{SUMMARY_INSTRUCTION}\n\nConversation:\n{transcript}"

    raw = generate_llm_reply(
        [{"role": "user", "content": instruction}], max_tokens=max_tokens
    )

    match = re.search(r"\{.*}", raw, re.DOTALL)
    json_text = match.group(0) if match else raw

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM summary as JSON, falling back to raw text: %s", raw)
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
    """True if the patient's message signals they want to end the intake chat."""
    lowered = message.lower()
    return any(phrase in lowered for phrase in TERMINATION_PHRASES)


_BOLD_ITALIC_RE = re.compile(r"\*\*(.*?)\*\*|\*(.*?)\*|__(.*?)__|_(.*?)_")
_HEADING_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^[ \t]*[\*\-•][ \t]+", re.MULTILINE)
_BACKTICK_RE = re.compile(r"`+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_llm_text(text: str) -> str:
    """Strip markdown formatting (**bold**, *italics*, #headings, backticks)
    and normalize bullets/whitespace so replies read cleanly in plain text."""

    def _unwrap(match: re.Match) -> str:
        return next(g for g in match.groups() if g is not None)

    text = _BOLD_ITALIC_RE.sub(_unwrap, text)
    text = _BACKTICK_RE.sub("", text)
    text = _HEADING_RE.sub("", text)
    text = _BULLET_RE.sub("- ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)

    return text.strip()
