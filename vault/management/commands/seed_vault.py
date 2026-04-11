"""Seed placeholder document records for the vault."""
from django.core.management.base import BaseCommand

from vault.models import Document

SEED_DOCS = [
    {
        "title": "K Wills Technologies LLC — Certificate of Formation",
        "category": "formation",
        "filename": "kwills-llc-formation.pdf",
        "file_type": "application/pdf",
        "file_size": 245_000,
        "description": "Texas Certificate of Formation for K Wills Technologies LLC.",
        "tags": "LLC, formation, Texas, K Wills Technologies",
    },
    {
        "title": "Nock Technologies — DBA Certificate",
        "category": "formation",
        "filename": "nock-dba-certificate.pdf",
        "file_type": "application/pdf",
        "file_size": 180_000,
        "description": "Assumed Name Certificate (DBA) for Nock Technologies.",
        "tags": "DBA, Nock Technologies, assumed name",
    },
    {
        "title": "NOCK — Trademark Application",
        "category": "trademark",
        "filename": "nock-trademark-application.pdf",
        "file_type": "application/pdf",
        "file_size": 520_000,
        "description": "USPTO trademark application for NOCK mark.",
        "tags": "trademark, USPTO, IP, NOCK",
    },
    {
        "title": "UpCounsel — Engagement Agreement",
        "category": "legal",
        "filename": "upcounsel-engagement.pdf",
        "file_type": "application/pdf",
        "file_size": 310_000,
        "description": "Legal services engagement agreement with UpCounsel.",
        "tags": "legal, UpCounsel, engagement, attorney",
    },
]


class Command(BaseCommand):
    help = "Seed placeholder document records in the vault."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--clear", action="store_true", help="Delete all vault documents first")

    def handle(self, *args, **options) -> None:
        if options["clear"]:
            for doc in Document.objects.all():
                if doc.file:
                    doc.file.delete(save=False)
            deleted, _ = Document.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} documents.")

        created = 0
        for doc_data in SEED_DOCS:
            _, was_created = Document.objects.get_or_create(
                title=doc_data["title"],
                defaults=doc_data,
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {created} vault documents."))
