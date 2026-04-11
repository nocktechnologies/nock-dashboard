"""Intelligence service functions — AI-powered features."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_morning_question() -> str | None:
    """Use Claude to generate a contextual morning question.

    Returns a single reflective question based on recent project context,
    or None if the API is unavailable.
    """
    from brain.models import MemoryEntry

    from . import ai_client

    recent = (
        MemoryEntry.objects.filter(
            category__in=["continuity", "project", "decision"],
        )
        .order_by("-updated_at")[:5]
    )

    context = "\n".join(
        f"- {e.category}/{e.key}: {e.preview}" for e in recent
    )

    result = ai_client.chat(
        messages=[{
            "role": "user",
            "content": f"Based on recent context:\n{context}\n\nGenerate one morning question.",
        }],
        system=(
            "Generate a single thoughtful reflective question based on the "
            "user's recent project context. The question should be reflective, "
            "not task-oriented. It can be about the business, strategy, or "
            "decisions to revisit. One question only, no preamble, no quotes. "
            "Keep it under 30 words."
        ),
        max_tokens=150,
    )

    if result is None:
        logger.info("AI question generation returned None — API unavailable")
        return None

    return result["content"].strip()
