"""
OpenAI embedding generation for the Research Library.

Uses text-embedding-3-small (1536 dims) for consistency across the entire
corpus. Supports batch embedding to reduce API overhead.

The OpenAI client is lazily instantiated so importing this module is safe
in environments without OPENAI_API_KEY configured (tests can mock these
functions directly).
"""
from __future__ import annotations

from django.conf import settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
# OpenAI's batch embedding endpoint accepts up to 2048 inputs per request.
# We default to a smaller batch to keep latency and error blast radius lower.
DEFAULT_BATCH_SIZE = 100
# The OpenAI Python SDK defaults to a 10-minute timeout per request, which is
# far too long for a hung connection inside a synchronous web request. Cap at
# 30s so /api/brain/research/search/ fails fast instead of pinning a worker.
DEFAULT_TIMEOUT_SECONDS = 30.0


def _get_client():
    """Lazily import and instantiate the OpenAI client.

    Importing at module load time would make the whole brain app fail to boot
    if openai isn't installed in the current environment.
    """
    from openai import OpenAI  # noqa: PLC0415 — intentional lazy import

    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in environment variables."
        )
    return OpenAI(api_key=api_key, timeout=DEFAULT_TIMEOUT_SECONDS)


def generate_embedding(text: str) -> list[float]:
    """Generate a single embedding vector for the given text."""
    if not text:
        raise ValueError("Cannot embed empty text")
    client = _get_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts in a single API call.

    Args:
        texts: List of input strings. Must be non-empty.

    Returns:
        List of embedding vectors, in the same order as the inputs.
    """
    if not texts:
        return []
    if any(not t for t in texts):
        raise ValueError("All texts in a batch must be non-empty")
    client = _get_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    # OpenAI preserves input order in response.data
    return [item.embedding for item in response.data]
