"""
Chunking logic for the Research Library.

Splits markdown documents into overlapping ~500-word chunks for embedding.
Tries to preserve semantic boundaries by splitting on markdown headers first,
then paragraphs, then raw word windows. Each chunk carries metadata pointing
back to its parent heading so search results can be displayed with context.
"""
from __future__ import annotations

import re
from typing import Any

HEADER_PATTERN = re.compile(r'^#{1,4} ')
HEADER_SPLIT_PATTERN = re.compile(r'\n(?=#{1,4} )')

DEFAULT_MAX_WORDS = 500
DEFAULT_OVERLAP_WORDS = 100


def chunk_document(
    content: str,
    title: str,
    topic: str,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[dict[str, Any]]:
    """
    Split a markdown document into overlapping chunks.

    Strategy:
    1. Split content on markdown headers (##, ###, ####) — these are natural
       semantic boundaries in the Kimi research files.
    2. Accumulate sections until hitting max_words, then emit a chunk.
    3. If a single section exceeds max_words, cut it into fixed-size windows
       (still with overlap_words of backfill from the prior window).
    4. Each chunk carries metadata (heading, topic, title) so search results
       can show where the chunk came from.

    Args:
        content: Full markdown document text.
        title: Document title (used in metadata).
        topic: Topic directory name (used in metadata).
        max_words: Target maximum words per chunk.
        overlap_words: Words to carry from the tail of one chunk into the next.

    Returns:
        List of dicts with keys: chunk_index, content, word_count, metadata.

    Raises:
        ValueError: if max_words is not a positive integer.
    """
    if max_words <= 0:
        raise ValueError("max_words must be greater than 0")
    if not content or not content.strip():
        return []

    # Clamp overlap to a sane fraction of max_words to avoid infinite loops.
    overlap_words = max(0, min(overlap_words, max_words - 1))

    chunks: list[dict[str, Any]] = []
    current_heading = title
    current_words: list[str] = []
    chunk_index = 0

    def _emit(words: list[str], heading: str) -> None:
        nonlocal chunk_index
        if not words:
            return
        chunks.append({
            'chunk_index': chunk_index,
            'content': ' '.join(words),
            'word_count': len(words),
            'metadata': {
                'heading': heading,
                'topic': topic,
                'title': title,
            },
        })
        chunk_index += 1

    sections = HEADER_SPLIT_PATTERN.split(content)

    for section in sections:
        if not section.strip():
            continue

        lines = section.lstrip().split('\n')
        section_heading = current_heading
        if lines and HEADER_PATTERN.match(lines[0]):
            section_heading = lines[0].lstrip('#').strip() or current_heading

        section_words = section.split()
        if not section_words:
            continue

        # Case 1: this section fits in the current chunk.
        if len(current_words) + len(section_words) <= max_words:
            # If current chunk is empty, adopt the section's heading so the
            # emitted chunk reflects where its content actually sits.
            if not current_words:
                current_heading = section_heading
            current_words.extend(section_words)
            continue

        # Case 2: flush the current chunk first (it has unfinished content).
        if current_words:
            _emit(current_words, current_heading)
            tail = current_words[-overlap_words:] if overlap_words else []
            current_words = list(tail)
            current_heading = section_heading

        # Case 3: the section alone exceeds max_words — window it.
        if len(current_words) + len(section_words) > max_words:
            combined = current_words + section_words
            start = 0
            while len(combined) - start > max_words:
                window = combined[start:start + max_words]
                _emit(window, section_heading)
                start += max(1, max_words - overlap_words)
            # Remainder becomes the seed of the next chunk.
            current_words = combined[start:]
            current_heading = section_heading
        else:
            current_words.extend(section_words)
            current_heading = section_heading

    # Flush the final chunk.
    _emit(current_words, current_heading)

    return chunks
