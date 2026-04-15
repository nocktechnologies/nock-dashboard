"""Phase 3: Backfill workspace FK on all tenant-scoped models.

Assigns every row with workspace=NULL to the first superuser's workspace.
Runs in batches of 1000 to avoid table locks on large datasets.
Safe to run on empty databases — exits early when no superuser workspace
exists (fresh installs that haven't gone through signup yet).

Reversal: sets all workspace columns back to NULL (Phase 4 makes them
non-nullable, so reversal of this migration must precede reversal of Phase 4).
"""
from __future__ import annotations

from django.db import migrations

BATCH_SIZE = 1000

# (app_label, model_name) — must match exact Django app labels
TENANT_MODELS = [
    ("pipeline", "Repository"),
    ("pipeline", "PullRequest"),
    ("pipeline", "PREvent"),
    ("pipeline", "Branch"),
    ("pipeline", "BranchEvent"),
    ("pipeline", "ReviewAlert"),
    ("pipeline", "PipelineEvent"),
    ("agent_sessions", "AgentSession"),
    ("agent_sessions", "SessionLog"),
    ("agent_sessions", "TerminalHeartbeat"),
    ("notifications", "NotificationChannel"),
    ("notifications", "NotificationRule"),
    ("notifications", "NotificationLog"),
    ("asana_tasks", "AsanaProject"),
    ("asana_tasks", "AsanaSection"),
    ("asana_tasks", "AsanaTask"),
    ("teams", "AgentTeam"),
    ("teams", "TeamMember"),
    ("teams", "TeamTask"),
    ("teams", "TeamEvent"),
    ("teams", "PromptFile"),
    ("teams", "PromptExecution"),
    ("context", "ContextDocument"),
    ("context", "ContextSnapshot"),
]


def _get_fallback_workspace(apps):
    """Return the first superuser's workspace, or None if none exists."""
    User = apps.get_model("auth", "User")
    WorkspaceMembership = apps.get_model("workspaces", "WorkspaceMembership")

    superuser = User.objects.filter(is_superuser=True).order_by("pk").first()
    if not superuser:
        return None

    membership = (
        WorkspaceMembership.objects.filter(
            user=superuser,
            accepted_at__isnull=False,
        )
        .select_related("workspace")
        .first()
    )
    return membership.workspace if membership else None


def backfill_workspace(apps, schema_editor):
    workspace = _get_fallback_workspace(apps)
    if workspace is None:
        # Fresh install with no superuser yet — nothing to backfill.
        return

    for app_label, model_name in TENANT_MODELS:
        Model = apps.get_model(app_label, model_name)
        while True:
            # Pull a batch of PKs that still need backfilling.
            batch_pks = list(
                Model.objects.filter(workspace__isnull=True)
                .values_list("pk", flat=True)[:BATCH_SIZE]
            )
            if not batch_pks:
                break
            Model.objects.filter(pk__in=batch_pks).update(workspace=workspace)


def reverse_backfill(apps, schema_editor):
    """Wipe the workspace column on all tenant models — prepares for Phase 2 rollback."""
    for app_label, model_name in TENANT_MODELS:
        Model = apps.get_model(app_label, model_name)
        while True:
            batch_pks = list(
                Model.objects.filter(workspace__isnull=False)
                .values_list("pk", flat=True)[:BATCH_SIZE]
            )
            if not batch_pks:
                break
            Model.objects.filter(pk__in=batch_pks).update(workspace=None)


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0001_initial"),
        ("pipeline", "0012_add_workspace_fk"),
        ("agent_sessions", "0004_add_workspace_fk"),
        ("notifications", "0003_add_workspace_fk"),
        ("asana_tasks", "0004_add_workspace_fk"),
        ("teams", "0007_add_workspace_fk"),
        ("context", "0003_add_workspace_fk"),
    ]

    operations = [
        migrations.RunPython(backfill_workspace, reverse_backfill),
    ]
