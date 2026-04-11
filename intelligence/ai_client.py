"""Anthropic API client wrapper for intelligence features."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# Pricing per million tokens (Sonnet 4.6)
INPUT_COST_PER_M = Decimal("3.00")
OUTPUT_COST_PER_M = Decimal("15.00")


def _get_client() -> Any | None:
    """Lazy-load the Anthropic client."""
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed — run: pip install anthropic")
        return None

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not configured")
        return None

    return anthropic.Anthropic(api_key=api_key)


def calculate_cost(input_tokens: int, output_tokens: int) -> Decimal:
    """Calculate cost in USD for a given token usage."""
    input_cost = Decimal(str(input_tokens)) * INPUT_COST_PER_M / Decimal("1000000")
    output_cost = Decimal(str(output_tokens)) * OUTPUT_COST_PER_M / Decimal("1000000")
    return input_cost + output_cost


def chat(
    messages: list[dict[str, str]],
    system: str = "",
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Send a chat request to Claude Sonnet.

    Returns dict with keys: content, input_tokens, output_tokens, cost, stop_reason
    Returns None if API unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools

    try:
        import anthropic

        response = client.messages.create(**kwargs)
    except ImportError:
        logger.error("anthropic package not available")
        return None
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        return None

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = calculate_cost(input_tokens, output_tokens)

    # Extract text content
    text_parts = []
    tool_uses = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_uses.append({
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })

    return {
        "content": "\n".join(text_parts),
        "tool_uses": tool_uses,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
        "stop_reason": response.stop_reason,
    }
