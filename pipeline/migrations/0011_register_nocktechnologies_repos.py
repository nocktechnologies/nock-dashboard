"""Register nocktechnologies org repositories."""

from django.conf import settings
from django.db import migrations

REPOS = [
    {"owner": "nocktechnologies", "name": "nocklock", "github_id": 1202244445},
    {"owner": "nocktechnologies", "name": "nocktechnologies.com", "github_id": 1204450384},
    {"owner": "nocktechnologies", "name": "nocktechnologies.io", "github_id": 1204450987},
]


def register_repos(apps, schema_editor):
    Repository = apps.get_model("pipeline", "Repository")
    secret = getattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    for repo in REPOS:
        Repository.objects.get_or_create(
            owner=repo["owner"],
            name=repo["name"],
            defaults={
                "github_id": repo["github_id"],
                "webhook_secret": "",
                "is_active": False,
            },
        )


def unregister_repos(apps, schema_editor):
    Repository = apps.get_model("pipeline", "Repository")
    Repository.objects.filter(owner="nocktechnologies").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pipeline", "0010_pipeline_event"),
    ]

    operations = [
        migrations.RunPython(register_repos, unregister_repos),
    ]
