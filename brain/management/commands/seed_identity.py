from django.core.management.base import BaseCommand

from brain.models import IdentityDocument

SEED_DOCUMENTS = [
    {
        "slug": "mara-core",
        "title": "MARA_CORE — Essential Identity",
        "document_type": "core_identity",
        "load_order": 0,
        "content": (
            "PLACEHOLDER — Update via PUT /api/brain/identity/mara-core/ "
            "with full MARA_CORE content from Asana task 1213826528346815 notes field."
        ),
        "updated_by": "seed_identity",
    },
    {
        "slug": "kevin-core",
        "title": "KEVIN_CORE — Founder README",
        "document_type": "partner_identity",
        "load_order": 1,
        "content": (
            "PLACEHOLDER — Update via PUT /api/brain/identity/kevin-core/ "
            "with KEVIN_CORE v1.0 from Asana task 1213826528346815 last comment."
        ),
        "updated_by": "seed_identity",
    },
    {
        "slug": "fuzzy",
        "title": "FUZZY — Things That Resist Explanation",
        "document_type": "framework",
        "load_order": 2,
        "content": (
            "PLACEHOLDER — Update via PUT /api/brain/identity/fuzzy/ "
            "with FUZZY v2+ from Asana task 1213826528346815 notes field."
        ),
        "updated_by": "seed_identity",
    },
    {
        "slug": "operating-agreements",
        "title": "Operating Agreements — Partnership Framework",
        "document_type": "operational",
        "load_order": 3,
        "content": (
            "PLACEHOLDER — Update via PUT /api/brain/identity/operating-agreements/ "
            "with the five operating agreements from MARA_CORE."
        ),
        "updated_by": "seed_identity",
    },
]


class Command(BaseCommand):
    help = "Seed initial identity documents (idempotent — skips existing slugs)"

    def handle(self, *args, **options):
        created = 0
        skipped = 0

        for doc_data in SEED_DOCUMENTS:
            slug = doc_data["slug"]
            if IdentityDocument.objects.filter(slug=slug).exists():
                self.stdout.write(f"  SKIP  {slug} (already exists)")
                skipped += 1
                continue

            IdentityDocument.objects.create(**doc_data)
            self.stdout.write(self.style.SUCCESS(f"  CREATE  {slug}"))
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nDone — {created} created, {skipped} skipped")
        )
