def mock_llm_reply(user_message: str) -> str:
    return f"I understand. Can you tell me more about: {user_message[:40]}"


def mock_summary(messages: list[dict]) -> dict:
    user_text = " ".join(m["content"] for m in messages if m["role"] == "user")

    return {
        "chief_complaint": user_text[:120],
        "risk_level": "medium",
        "recommended_speciality": "general_practice",
        "summary": user_text[:300]
    }
