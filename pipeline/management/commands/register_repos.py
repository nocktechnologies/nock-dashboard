from django.conf import settings
from django.core.management.base import BaseCommand

from pipeline.models import Repository

REPOS = [
    {"owner": "kkwills13", "name": "project-nexus", "github_id": 1},
    {"owner": "kkwills13", "name": "nock-command-center", "github_id": 2},
    {"owner": "kkwills13", "name": "Project-Nexus---ABL", "github_id": 3},
    {"owner": "kkwills13", "name": "Nexus-po_hub", "github_id": 4},
    {"owner": "kkwills13", "name": "github.com-kkwills13-nock-technologies-site", "github_id": 5},
    {"owner": "kkwills13", "name": "Forge", "github_id": 6},
    {"owner": "kkwills13", "name": "jobcost", "github_id": 7},
    {"owner": "kkwills13", "name": "claude-terminal", "github_id": 8},
    # nocktechnologies org repos
    {"owner": "nocktechnologies", "name": "nocklock", "github_id": 1202244445},
    {"owner": "nocktechnologies", "name": "nocktechnologies.com", "github_id": 1204450384},
    {"owner": "nocktechnologies", "name": "nocktechnologies.io", "github_id": 1204450987},
]


class Command(BaseCommand):
    help = "Register the five core Nock repositories (idempotent)."

    def handle(self, *args, **options):
        secret = settings.GITHUB_WEBHOOK_SECRET
        if not secret:
            self.stderr.write(self.style.ERROR("GITHUB_WEBHOOK_SECRET is not set."))
            return

        for repo in REPOS:
            _, created = Repository.objects.get_or_create(
                owner=repo["owner"],
                name=repo["name"],
                defaults={
                    "github_id": repo["github_id"],
                    "webhook_secret": secret,
                },
            )
            status = "created" if created else "exists"
            self.stdout.write(f"  {repo['owner']}/{repo['name']} — {status}")

        self.stdout.write(self.style.SUCCESS("Done."))
