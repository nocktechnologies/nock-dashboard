from django.core.management.base import BaseCommand
from django.db.models import Count

from pipeline.models import Repository


class Command(BaseCommand):
    help = "Merge duplicate Repository records (same owner+name) — keeps the one with the most PRs."

    def handle(self, *args: object, **options: object) -> None:
        dupes = (
            Repository.objects.values("owner", "name")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
            .order_by("owner", "name")
        )

        if not dupes:
            self.stdout.write(self.style.SUCCESS("No duplicate repositories found."))
            return

        for group in dupes:
            owner, name = group["owner"], group["name"]
            repos = list(
                Repository.objects.filter(owner=owner, name=name)
                .annotate(pr_count=Count("pull_requests"))
                .order_by("-pr_count", "pk")
            )

            keeper = repos[0]
            duplicates = repos[1:]
            self.stdout.write(f"  {owner}/{name}: keeping pk={keeper.pk} ({keeper.pr_count} PRs)")

            for dup in duplicates:
                # Reassign related objects to the keeper
                dup.pull_requests.update(repository=keeper)
                dup.branches.update(repository=keeper)
                dup.branch_events.update(repository=keeper)
                dup.sessions.update(repository=keeper)
                self.stdout.write(f"    deleted duplicate pk={dup.pk} (github_id={dup.github_id})")
                dup.delete()

        self.stdout.write(self.style.SUCCESS("Duplicate cleanup complete."))
