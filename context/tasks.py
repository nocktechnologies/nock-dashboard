"""Celery tasks for context document syncing."""

import logging

from celery import shared_task

from .github_sync import sync_context_documents

logger = logging.getLogger(__name__)


@shared_task
def sync_context_docs_task() -> dict[str, int]:
    """Periodic task to sync all active context documents from GitHub."""
    result = sync_context_documents()
    log = logger.warning if result["errors"] else logger.info
    log(
        "Context sync complete: %d updated, %d unchanged, %d errors",
        result["updated"],
        result["unchanged"],
        result["errors"],
    )
    return result

