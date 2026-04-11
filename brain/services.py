"""Brain consolidation engine and morning note generator."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class BrainConsolidator:
    """Four-phase consolidation engine for Brain entries.

    Three-gate trigger: 24h since last, 5+ updates since last, no lock held.
    Phases: orient, gather signal, consolidate, prune.
    """

    STALE_DAYS = 60
    PRUNE_DAYS = 90
    MAX_ENTRIES = 200
    MAX_TEXT_BYTES = 25_000

    def run(self, force: bool = False) -> dict:
        from .models import ConsolidationLog, MemoryEntry

        # Gate check (skippable with force=True)
        if not force:
            gate_result = self._check_gates()
            if gate_result:
                return gate_result

        # Acquire lock atomically — if another process slipped through gates,
        # the unique incomplete log check prevents double-runs.
        log = ConsolidationLog.objects.create()

        try:
            # Phase 1: Orient
            total = MemoryEntry.objects.count()
            log.entries_reviewed = total

            # Phase 2: Gather signal
            last_log = (
                ConsolidationLog.objects.exclude(pk=log.pk)
                .order_by("-started_at")
                .first()
            )
            since = last_log.started_at if last_log else timezone.now() - timedelta(days=365)
            recent = MemoryEntry.objects.filter(
                Q(created_at__gte=since) | Q(updated_at__gte=since)
            )

            stale_cutoff = timezone.now() - timedelta(days=self.STALE_DAYS)
            stale_entries = MemoryEntry.objects.filter(updated_at__lt=stale_cutoff)

            notes_parts = []

            # Phase 3: Consolidate
            promoted = self._promote_confidence(recent)
            log.entries_promoted = promoted
            if promoted:
                notes_parts.append(f"Promoted {promoted} entries to observed")

            resolved = self._resolve_contradictions()
            log.contradictions_resolved = resolved
            if resolved:
                notes_parts.append(f"Resolved {resolved} contradictions")

            merged = self._merge_duplicates()
            if merged:
                notes_parts.append(f"Merged {merged} duplicate entries")

            archived = self._archive_stale(stale_entries)
            log.entries_archived = archived
            if archived:
                notes_parts.append(f"Archived {archived} stale entries")

            # Phase 4: Prune
            pruned = self._prune(MemoryEntry)
            log.entries_pruned = pruned
            if pruned:
                notes_parts.append(f"Pruned {pruned} dead entries")

            log.notes = "; ".join(notes_parts) if notes_parts else "No changes needed"
            log.completed_at = timezone.now()
            log.save()

            return {
                "skipped": False,
                "log_id": log.pk,
                "entries_reviewed": log.entries_reviewed,
                "entries_promoted": log.entries_promoted,
                "entries_archived": log.entries_archived,
                "entries_pruned": log.entries_pruned,
                "contradictions_resolved": log.contradictions_resolved,
                "notes": log.notes,
            }
        except Exception:
            log.notes = "Consolidation failed"
            log.completed_at = timezone.now()
            log.save()
            logger.exception("Consolidation failed")
            raise

    def _check_gates(self) -> dict | None:
        """Check three-gate trigger. Returns skip dict if any gate fails, None if all pass."""
        from .models import ConsolidationLog, MemoryEntry

        now = timezone.now()
        last_log = (
            ConsolidationLog.objects.filter(completed_at__isnull=False)
            .order_by("-started_at")
            .first()
        )

        # Gate 1: 24 hours since last consolidation
        if last_log and (now - last_log.started_at) < timedelta(hours=24):
            next_eligible = last_log.started_at + timedelta(hours=24)
            return {
                "skipped": True,
                "reason": "Less than 24 hours since last consolidation",
                "next_eligible": next_eligible.isoformat(),
            }

        # Gate 2: At least 5 updates since last consolidation
        since = last_log.started_at if last_log else now - timedelta(days=365)
        updates_since = MemoryEntry.objects.filter(updated_at__gte=since).count()
        if updates_since < 5:
            return {
                "skipped": True,
                "reason": f"Only {updates_since} updates since last consolidation (need 5)",
                "next_eligible": None,
            }

        # Gate 3: No lock held (incomplete consolidation)
        running = ConsolidationLog.objects.filter(completed_at__isnull=True).exists()
        if running:
            return {
                "skipped": True,
                "reason": "Consolidation already in progress",
                "next_eligible": None,
            }

        return None

    def _promote_confidence(self, recent_entries) -> int:
        """Promote inferred entries within the recent window to observed."""
        promoted = 0
        inferred = recent_entries.filter(confidence="inferred")
        for entry in inferred:
            if len(entry.tags) >= 2 or entry.source in ("session", "diary"):
                entry.confidence = "observed"
                entry.save(update_fields=["confidence"])
                promoted += 1
        return promoted

    def _resolve_contradictions(self) -> int:
        """If two entries share the same key in the same category, keep newer one."""
        from .models import MemoryEntry

        resolved = 0
        seen: dict[tuple[str, str], int] = {}

        for entry in MemoryEntry.objects.order_by("category", "key", "-updated_at", "pk"):
            combo = (entry.category, entry.key)
            if combo in seen:
                entry.confidence = "stale"
                entry.save(update_fields=["confidence"])
                resolved += 1
            else:
                seen[combo] = entry.pk
        return resolved

    def _merge_duplicates(self) -> int:
        """Merge entries with identical keys in the same category.

        Shouldn't exist due to unique_together, but defensive.
        """
        return 0

    def _archive_stale(self, stale_entries) -> int:
        """Archive entries that haven't been updated in STALE_DAYS."""
        archived = 0
        for entry in stale_entries:
            if entry.confidence != "stale":
                entry.confidence = "stale"
                entry.save(update_fields=["confidence"])
                archived += 1
        return archived

    def _prune(self, model_class) -> int:
        """Delete entries that have been stale for PRUNE_DAYS. Cap total at MAX_ENTRIES."""
        prune_cutoff = timezone.now() - timedelta(days=self.PRUNE_DAYS)
        dead = model_class.objects.filter(
            confidence="stale",
            updated_at__lt=prune_cutoff,
        )
        pruned = dead.count()
        dead.delete()

        # Cap at MAX_ENTRIES — evict stale first, then oldest non-stale
        total = model_class.objects.count()
        if total > self.MAX_ENTRIES:
            excess = total - self.MAX_ENTRIES
            # Try stale entries first
            stale_to_remove = (
                model_class.objects.filter(confidence="stale")
                .order_by("updated_at", "pk")[:excess]
            )
            stale_ids = list(stale_to_remove.values_list("pk", flat=True))
            if stale_ids:
                model_class.objects.filter(pk__in=stale_ids).delete()
                pruned += len(stale_ids)
                excess -= len(stale_ids)

            # If still over cap, evict oldest entries regardless of confidence
            if excess > 0:
                oldest_to_remove = (
                    model_class.objects.order_by("updated_at", "pk")[:excess]
                )
                oldest_ids = list(oldest_to_remove.values_list("pk", flat=True))
                if oldest_ids:
                    model_class.objects.filter(pk__in=oldest_ids).delete()
                    pruned += len(oldest_ids)

        return pruned


_MD_ESCAPE_RE = re.compile(r"([_*\[\]`])")


def _escape_markdown(text: str) -> str:
    """Escape Telegram Markdown special characters in dynamic content."""
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


class MorningNoteGenerator:
    """Generate Mara's Morning Note for Telegram."""

    def generate(self) -> str | None:
        thinking = self._get_thinking_section()
        matters = self._get_matters_section()
        question = self._get_question()

        date_str = timezone.now().strftime("%B %d, %Y").replace(" 0", " ")

        note = f"\u2600\ufe0f *Mara's Morning Note* \u2014 {date_str}\n\n"
        note += f"*What I'm thinking about:*\n{thinking}\n\n"
        note += f"*What matters today:*\n{matters}\n\n"
        note += f"*A question for your commute:*\n{question}"

        return note

    def _get_thinking_section(self) -> str:
        """Pull the most recently updated continuity entry."""
        from .models import MemoryEntry

        entry = (
            MemoryEntry.objects.filter(category="continuity")
            .order_by("-updated_at", "-pk")
            .first()
        )

        if entry:
            sentences = entry.value.split(".")
            preview = ". ".join(s.strip() for s in sentences[:3] if s.strip())
            if preview and not preview.endswith("."):
                preview += "."
            return _escape_markdown(preview)
        return "Starting fresh today. Let's see what we build."

    def _get_matters_section(self) -> str:
        """Pull from Asana tasks due today + pipeline open PRs."""
        items: list[str] = []

        # Asana tasks due today
        try:
            from tasks.models import AsanaTask

            today = timezone.now().date()
            tasks = AsanaTask.objects.filter(
                completed=False,
                due_on=today,
            ).order_by("name", "pk")[:2]
            for task in tasks:
                items.append(f"\u2022 {_escape_markdown(task.name)}")
        except ImportError:
            logger.debug("tasks app not available for morning note")

        # Pipeline — open PRs
        try:
            from pipeline.models import PullRequest

            prs = (
                PullRequest.objects.filter(state=PullRequest.State.OPEN)
                .select_related("repository")
                .order_by("-opened_at", "-pk")[:1]
            )
            for pr in prs:
                items.append(f"\u2022 PR #{pr.number} {_escape_markdown(pr.title)} \u2014 {pr.state}")
        except ImportError:
            logger.debug("pipeline app not available for morning note")

        # Fill to 3 items from project entries
        if len(items) < 3:
            from .models import MemoryEntry

            projects = (
                MemoryEntry.objects.filter(category="project")
                .order_by("-updated_at", "-pk")[: 3 - len(items)]
            )
            for p in projects:
                items.append(f"\u2022 {_escape_markdown(p.key)} \u2014 check in")

        return "\n".join(items[:3]) if items else "\u2022 Clear slate today"

    def _get_question(self) -> str:
        """Generate a thoughtful question using the AI Advisor, with fallback."""
        from django.conf import settings

        if not getattr(settings, "MORNING_NOTE_AI_QUESTIONS", True):
            return self._fallback_question()

        try:
            from intelligence.services import generate_morning_question

            question = generate_morning_question()
            if question:
                return question
        except ImportError:
            logger.debug("intelligence app not available for morning question")
        return self._fallback_question()

    @staticmethod
    def _fallback_question() -> str:
        """Rotating fallback questions if AI Advisor is unavailable."""
        questions = [
            "What's the one thing you'd build this week if nothing else mattered?",
            "When's the last time you did something just because it was fun?",
            "If Nexus had to launch with only three features, which three?",
            "What's the biggest risk you're not talking about?",
            "What would you tell yourself six months ago about where you are now?",
            "What's one thing that's working really well that you haven't celebrated?",
            "If you could only keep one tool from your stack, which one?",
            "What does 'done' look like for this month?",
            "What would the partnership look like in six months if everything goes right?",
            "What are you avoiding that you know needs attention?",
            "What's the most valuable thing you learned this week that isn't about code?",
            "If someone handed you a free week with no obligations, what would you build?",
            "What's one habit from your factoring career that you've brought into building?",
            "What's the conversation you need to have but keep putting off?",
        ]
        day_of_year = timezone.now().timetuple().tm_yday
        return questions[day_of_year % len(questions)]
