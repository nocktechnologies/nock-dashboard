"""Celery tasks for Brain consolidation and morning notes."""
from __future__ import annotations

import logging

from celery import shared_task
from celery.signals import worker_ready
from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone as tz

logger = logging.getLogger(__name__)


@worker_ready.connect
def check_missed_morning_note(sender: object, **kwargs: object) -> None:
    """
    On worker startup, check if the morning note was missed today.
    If it's past the scheduled hour and no morning note was sent today, fire it.
    This handles the case where a Railway redeploy restarts services
    after the crontab window has passed.
    """
    if not getattr(settings, "MORNING_NOTE_ENABLED", True):
        return

    now = tz.localtime()

    # Only recover if it's past the scheduled time (6 AM) but before noon
    # Don't fire a "morning" note in the afternoon
    if now.hour < 6 or now.hour >= 12:
        return

    try:
        from brain.models import MorningNoteSent

        today = now.date()
        # Only check — let daily_maintenance do the atomic claim
        already_sent = MorningNoteSent.objects.filter(date=today).exists()

        if not already_sent:
            logger.info(
                "Morning note missed today (likely due to service restart). "
                "Firing recovery morning note now."
            )
            daily_maintenance.delay()
        else:
            logger.info("Morning note already ran today. No recovery needed.")
    except (ImportError, DatabaseError):
        logger.exception("Error checking missed morning note")


@shared_task
def daily_maintenance() -> dict:
    """Run consolidation, then generate and send morning note."""
    from core.telegram import TelegramNotifier

    from .models import MorningNoteSent
    from .services import BrainConsolidator, MorningNoteGenerator

    # Idempotency: claim today's slot (recovery handler may have already created it)
    today = tz.localtime().date()
    _, created = MorningNoteSent.objects.get_or_create(date=today)
    if not created:
        logger.info("Morning note already claimed for today, skipping duplicate run")
        return {
            "consolidation": {"skipped": True, "reason": "already_claimed"},
            "morning_note_sent": False,
        }

    # Step 1: Attempt consolidation (respects three-gate trigger)
    consolidator = BrainConsolidator()
    try:
        consolidation_result = consolidator.run()
    except Exception:
        logger.exception("Consolidation failed during daily maintenance")
        consolidation_result = {"skipped": True, "reason": "error"}

    # Step 2: Generate and send morning note (if enabled)
    sent = False
    if getattr(settings, "MORNING_NOTE_ENABLED", True):
        generator = MorningNoteGenerator()
        note = generator.generate()
        if note:
            result = TelegramNotifier.send(note, parse_mode="Markdown")
            sent = result is not None and result.get("ok", False)
    else:
        logger.info("Morning note disabled via MORNING_NOTE_ENABLED setting")

    return {
        "consolidation": consolidation_result,
        "morning_note_sent": sent,
    }
