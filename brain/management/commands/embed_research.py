"""
embed_research — chunk unindexed ResearchDocuments and generate embeddings.

Usage:
    python manage.py embed_research
    python manage.py embed_research --batch-size 100
    python manage.py embed_research --topic abl-underwriting
    python manage.py embed_research --force
"""
from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import transaction

from brain import embeddings
from brain.chunking import chunk_document
from brain.models import ResearchChunk, ResearchDocument

# text-embedding-3-small costs $0.02 per 1M tokens. 1 token ~= 0.75 words, so
# every ~750 words is ~1000 tokens = $0.00002. We display a rough estimate.
COST_PER_1M_TOKENS = 0.02
APPROX_TOKENS_PER_WORD = 1.3


@dataclass
class EmbedStats:
    documents_processed: int = 0
    documents_skipped: int = 0
    chunks_created: int = 0
    embeddings_generated: int = 0
    total_words: int = 0


class Command(BaseCommand):
    help = "Chunk ResearchDocuments and generate OpenAI embeddings for each chunk."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of chunks to embed per OpenAI API call (max 2048)",
        )
        parser.add_argument(
            "--topic",
            type=str,
            default=None,
            help="Only embed documents in this topic",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-embed already-indexed documents",
        )
        parser.add_argument(
            "--max-documents",
            type=int,
            default=None,
            help="Stop after processing this many documents (useful for testing)",
        )

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        batch_size: int = max(1, min(int(options["batch_size"]), 2048))
        topic_filter: str | None = options["topic"]
        force: bool = options["force"]
        max_documents: int | None = options["max_documents"]

        qs = ResearchDocument.objects.all().order_by("topic", "title")
        if not force:
            qs = qs.filter(is_indexed=False)
        if topic_filter:
            qs = qs.filter(topic=topic_filter)
        # Explicit None check so --max-documents=0 slices to an empty queryset
        # instead of being treated as "no limit".
        if max_documents is not None:
            qs = qs[:max_documents]

        stats = EmbedStats()
        # Grab only the primary keys up front. We re-fetch each row inside its
        # own transaction with select_for_update() so a concurrent
        # `ingest_research` run can't race us into embedding stale content and
        # then flipping is_indexed=True on a newer revision of the row.
        doc_ids = list(qs.values_list("pk", flat=True))
        self.stdout.write(f"Embedding {len(doc_ids)} document(s)...")

        for doc_id in doc_ids:
            with transaction.atomic():
                try:
                    doc = (
                        ResearchDocument.objects.select_for_update().get(pk=doc_id)
                    )
                except ResearchDocument.DoesNotExist:
                    # Deleted between snapshot and processing — skip.
                    stats.documents_skipped += 1
                    continue

                # Another worker may have indexed this row while we were
                # waiting on the lock. Without --force, skip to avoid paying
                # for a duplicate embedding pass and rewriting identical chunks.
                if not force and doc.is_indexed:
                    stats.documents_skipped += 1
                    continue

                if not doc.content.strip():
                    stats.documents_skipped += 1
                    continue

                chunk_dicts = chunk_document(
                    content=doc.content,
                    title=doc.title,
                    topic=doc.topic,
                )
                if not chunk_dicts:
                    stats.documents_skipped += 1
                    continue

                texts = [c["content"] for c in chunk_dicts]

                # Embed in batches to respect rate limits and minimize retry
                # blast radius. We hold the row lock for the duration of the
                # embed call — acceptable because this is a background command
                # and concurrent writers (ingest_research) should wait rather
                # than race.
                all_vectors: list[list[float]] = []
                for start in range(0, len(texts), batch_size):
                    batch = texts[start:start + batch_size]
                    vectors = embeddings.generate_embeddings_batch(batch)
                    all_vectors.extend(vectors)
                    stats.embeddings_generated += len(vectors)

                doc.chunks.all().delete()
                new_chunks = [
                    ResearchChunk(
                        document=doc,
                        chunk_index=c["chunk_index"],
                        content=c["content"],
                        word_count=c["word_count"],
                        metadata=c["metadata"],
                        embedding=vec,
                    )
                    for c, vec in zip(chunk_dicts, all_vectors, strict=True)
                ]
                ResearchChunk.objects.bulk_create(new_chunks)
                doc.is_indexed = True
                doc.save(update_fields=["is_indexed", "updated_at"])

            stats.chunks_created += len(chunk_dicts)
            stats.total_words += sum(c["word_count"] for c in chunk_dicts)
            stats.documents_processed += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"  EMBED  {doc.topic}/{doc.slug} ({len(chunk_dicts)} chunks)"
                )
            )

        estimated_tokens = stats.total_words * APPROX_TOKENS_PER_WORD
        estimated_cost = (estimated_tokens / 1_000_000) * COST_PER_1M_TOKENS

        self.stdout.write(
            self.style.SUCCESS(
                "\nDone — "
                f"{stats.documents_processed} docs processed, "
                f"{stats.documents_skipped} skipped, "
                f"{stats.chunks_created} chunks created, "
                f"{stats.embeddings_generated} embeddings generated. "
                f"Estimated cost: ${estimated_cost:.4f}"
            )
        )
