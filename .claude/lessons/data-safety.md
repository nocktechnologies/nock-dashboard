# Lesson: Data Safety Patterns

## Money / Decimal Handling
- All money values: `Decimal(str(value))` — never float, never `Decimal(float_value)`
- Float arithmetic introduces rounding errors that compound across transactions

## Database Atomicity
- All DB writes that touch balances or state: `transaction.atomic()` + `select_for_update()`
- Use `F()` expressions for counter increments to prevent race conditions
- All querysets must have deterministic ordering (`.order_by(...)`)

## Idempotency
- GitHub webhook processing uses delivery_id tracking (PREvent, BranchEvent) for dedup
- ReviewAlert and PredictiveAlert use time-window checks + IntegrityError handling (two-layer dedup)
- SmartWatchRule uses select_for_update() + cooldown_minutes for atomic state transitions

## Notifications
- Use `transaction.on_commit()` for side effects (Telegram, Slack) so they only fire after DB commit succeeds
- Pipeline tasks wrap `_send_review_telegram()` and `_link_review_to_team_task()` in on_commit callbacks
