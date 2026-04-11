# ADR-003: Pseudo-Signal Pattern for Pipeline ↔ Teams Integration

**Status:** Accepted
**Date:** 2026-03-31

## Context
When GitHub PRs are opened/merged/reviewed, the teams app needs to update TeamTask status, PromptFile lifecycle, and fire Telegram notifications.

## Decision
Direct function calls from `pipeline.tasks` to `teams.signals` module functions (not Django model signals).

## Rationale
- Django signals are implicit and hard to debug — direct calls are explicit and traceable
- The functions (`on_pr_opened`, `on_pr_merged`, `on_review_alert`, `on_prompt_pr_review`, `on_prompt_pr_merged`) have clear names showing the event contract
- Review path (`_link_review_to_team_task`, `_send_review_telegram`) is wrapped in `transaction.on_commit()`
- PR open/merge paths (`_link_pr_to_team_task`, `_complete_team_task_on_merge`) are called directly from task helpers
- Easier to test — call the function directly with known arguments

## Consequences
- pipeline app has import dependency on teams.signals (acceptable — pipeline is upstream)
- If teams app is removed, pipeline tasks need corresponding cleanup
- New cross-app events should follow the same pattern: named function in target app's signals.py
