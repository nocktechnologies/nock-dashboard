import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Value
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone

logger = logging.getLogger(__name__)

_STALE_NOTE = "\nAuto-completed: no activity for 2+ hours."


@shared_task
def cleanup_stale_sessions() -> int:
    """Mark active sessions as completed if no activity for 2+ hours."""
    from .models import AgentSession

    cutoff = timezone.now() - timedelta(hours=2)
    stale_qs = AgentSession.objects.filter(
        status="active",
        last_activity__lt=cutoff,
    )
    count = stale_qs.update(
        status="completed",
        ended_at=timezone.now(),
        notes=Concat(Coalesce("notes", Value("")), Value(_STALE_NOTE)),
    )
    if count:
        logger.info("Cleaned up %d stale session(s).", count)
    return count
