"""
search_research — quick CLI test for the semantic search pipeline.

Usage:
    python manage.py search_research "reserve methodology for transportation debtors"
    python manage.py search_research "..." --limit 5
    python manage.py search_research "..." --topic abl-underwriting
"""
from __future__ import annotations

import textwrap

from django.core.management.base import BaseCommand
from pgvector.django import CosineDistance

from brain import embeddings
from brain.models import ResearchChunk


class Command(BaseCommand):
    help = "Run a semantic search query against the research library."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument("query", type=str, help="Natural language search query")
        parser.add_argument("--limit", type=int, default=5, help="Max number of results")
        parser.add_argument("--topic", type=str, default=None, help="Optional topic filter")

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        query: str = options["query"]
        limit: int = max(1, int(options["limit"]))
        topic: str | None = options["topic"]

        self.stdout.write(f"Query: {query!r}")
        if topic:
            self.stdout.write(f"Topic filter: {topic}")

        query_embedding = embeddings.generate_embedding(query)

        qs = ResearchChunk.objects.filter(
            embedding__isnull=False,
            document__is_indexed=True,
        ).select_related("document")
        if topic:
            qs = qs.filter(document__topic=topic)

        results = (
            qs.annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:limit]
        )

        hits = list(results)
        if not hits:
            self.stdout.write(self.style.WARNING("No results."))
            return

        self.stdout.write(f"\nTop {len(hits)} results:\n")
        for rank, chunk in enumerate(hits, start=1):
            score = round(1 - float(chunk.distance), 4)
            heading = (chunk.metadata or {}).get("heading", "")
            snippet = textwrap.shorten(chunk.content, width=240, placeholder="...")
            self.stdout.write(
                f"{rank}. [{score:.4f}] {chunk.document.topic}/{chunk.document.title}"
            )
            if heading:
                self.stdout.write(f"    § {heading}")
            self.stdout.write(f"    {snippet}\n")
