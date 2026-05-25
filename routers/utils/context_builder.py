"""Presentation-layer utility: build LLM context from conversation messages.

Not part of the DAG runtime — lives here because it's only used by routers.
"""

from typing import List, Dict
import re

MAX_CONTEXT_MESSAGES = 12
MAX_MESSAGE_LENGTH = 1200


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH] + "..."
    return text.strip()


def build_conversation_context(messages: List[Dict]) -> str:
    if not messages:
        return ""

    recent_messages = messages[-MAX_CONTEXT_MESSAGES:]
    context_parts = []

    for msg in recent_messages:
        role = msg.get("role", "user").strip().upper()
        content = msg.get("content", "")
        content = _clean_text(content)
        if not content:
            continue
        if role not in ("USER", "ASSISTANT", "SYSTEM"):
            role = "USER"
        context_parts.append(f"{role}: {content}")

    return "\n".join(context_parts)
