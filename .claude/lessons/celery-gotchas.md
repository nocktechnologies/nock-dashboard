# Lesson: Celery Task Gotchas

## Morning Note Recovery
- Railway redeploys can cause the daily_maintenance task to miss its window
- Solution: `check_missed_morning_note()` fires on `worker_ready` signal to catch missed runs
- Always check `MorningNoteSent` for today's date before sending

## Task Idempotency
- All webhook-triggered tasks must handle duplicate delivery (GitHub retries on timeout)
- Pattern: check for existing PREvent/BranchEvent by delivery_id before processing
- Use IntegrityError catch as second layer of defense

## Timezone
- Celery Beat uses America/Denver timezone
- All crontab schedules defined in `config/settings/base.py` CELERY_BEAT_SCHEDULE
- Weekly memo runs Monday 7 AM MT, not UTC

## Cross-App Integration
- `teams/signals.py` functions are NOT Django signals — they're called directly from pipeline.tasks
- Review path (`_create_review_alert`) wraps cross-app calls in `transaction.on_commit()`
- PR open/merge paths call `teams.signals` directly from helper functions
- New cross-app side effects should use `transaction.on_commit()` to match the review-path pattern
