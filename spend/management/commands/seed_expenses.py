"""Seed real business expenses from Asana tracking."""

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from spend.models import Expense

EXPENSES = [
    {
        "vendor": "Anthropic",
        "description": "Claude Max 5x (Feb 10-Mar 10) incl -$6.57 prorated credit",
        "category": "software",
        "subtotal": Decimal("93.43"),
        "tax": Decimal("5.42"),
        "total": Decimal("98.85"),
        "payment_method": "card_a",
        "reference": "INV EY6LYZPH-0003",
        "date": date(2026, 2, 10),
    },
    {
        "vendor": "Anthropic",
        "description": "Claude Max 20x (Feb 21-Mar 21) incl -$59.96 prorated credit",
        "category": "software",
        "subtotal": Decimal("140.04"),
        "tax": Decimal("8.12"),
        "total": Decimal("148.16"),
        "payment_method": "card_a",
        "reference": "INV EY6LYZPH-0004",
        "date": date(2026, 2, 21),
    },
    {
        "vendor": "Apple Store",
        "description": "MacBook Air M4 24GB/512GB (MC6C4LL/A) Serial H4Y4NQW372",
        "category": "hardware",
        "subtotal": Decimal("1399.00"),
        "tax": Decimal("115.42"),
        "total": Decimal("1514.42"),
        "payment_method": "card_b",
        "reference": "Order W1353016783",
        "date": date(2026, 2, 23),
    },
    {
        "vendor": "OpenAI",
        "description": "ChatGPT Plus Subscription (per seat)",
        "category": "software",
        "subtotal": Decimal("21.28"),
        "tax": Decimal("0.00"),
        "total": Decimal("21.28"),
        "payment_method": "card_c",
        "reference": "OpenAI billing",
        "date": date(2026, 2, 22),
    },
    {
        "vendor": "Moonshot AI",
        "description": "Kimi subscription (Feb 23-Mar 23)",
        "category": "software",
        "subtotal": Decimal("39.00"),
        "tax": Decimal("0.00"),
        "total": Decimal("39.00"),
        "payment_method": "card_c",
        "reference": "INV F8NXMRYN-0001",
        "date": date(2026, 2, 23),
    },
    {
        "vendor": "Moonshot AI",
        "description": "REFUND — Kimi order change (upgrade to $99 plan)",
        "category": "software",
        "subtotal": Decimal("36.21"),
        "tax": Decimal("0.00"),
        "total": Decimal("36.21"),
        "is_refund": True,
        "payment_method": "card_c",
        "reference": "Credit Note F8NXMRYN-0001-CN-01",
        "date": date(2026, 2, 25),
    },
    {
        "vendor": "Moonshot AI",
        "description": "Kimi upgraded subscription (Feb 25-Mar 25)",
        "category": "software",
        "subtotal": Decimal("99.00"),
        "tax": Decimal("0.00"),
        "total": Decimal("99.00"),
        "payment_method": "stripe_link",
        "reference": "INV F8NXMRYN-0002",
        "date": date(2026, 2, 25),
    },
    {
        "vendor": "Anthropic",
        "description": "One-time credit purchase",
        "category": "software",
        "subtotal": Decimal("20.00"),
        "tax": Decimal("1.16"),
        "total": Decimal("21.16"),
        "payment_method": "stripe_link",
        "reference": "INV W8BGY8AS-0001",
        "date": date(2026, 2, 26),
    },
    {
        "vendor": "Vercel (v0)",
        "description": "v0 Subscription",
        "category": "software",
        "subtotal": Decimal("20.00"),
        "tax": Decimal("1.32"),
        "total": Decimal("21.32"),
        "payment_method": "stripe_link",
        "reference": "INV RBQMDYPF-0001",
        "date": date(2026, 3, 5),
    },
    {
        "vendor": "CodeRabbit",
        "description": "CodeRabbit Pro (Monthly) Mar 6-Apr 6",
        "category": "software",
        "subtotal": Decimal("30.00"),
        "tax": Decimal("0.00"),
        "total": Decimal("30.00"),
        "payment_method": "card_c",
        "reference": "INV CR-2026-03-140561",
        "date": date(2026, 3, 6),
    },
    {
        "vendor": "Namecheap",
        "description": "3 domains (nocktechnologies.com, .io, nocktech.io) + privacy",
        "category": "domains",
        "subtotal": Decimal("80.84"),
        "tax": Decimal("0.00"),
        "total": Decimal("80.84"),
        "payment_method": "card_c",
        "reference": "Order #196412391",
        "date": date(2026, 3, 6),
    },
    {
        "vendor": "TX Sec of State",
        "description": "Name Availability search — K Wills Technologies",
        "category": "formation",
        "subtotal": Decimal("1.00"),
        "tax": Decimal("0.00"),
        "total": Decimal("1.00"),
        "payment_method": "card_a",
        "reference": "Batch 156484476",
        "date": date(2026, 3, 6),
    },
    {
        "vendor": "TX Sec of State",
        "description": "Certificate of Formation — K Wills Technologies LLC",
        "category": "formation",
        "subtotal": Decimal("300.00"),
        "tax": Decimal("0.00"),
        "total": Decimal("300.00"),
        "payment_method": "card_a",
        "reference": "Batch 156485040",
        "date": date(2026, 3, 6),
    },
    {
        "vendor": "Anthropic",
        "description": "Prepaid extra usage",
        "category": "software",
        "subtotal": Decimal("50.00"),
        "tax": Decimal("2.90"),
        "total": Decimal("52.90"),
        "payment_method": "card_a",
        "reference": "INV EY6LYZPH-0005",
        "date": date(2026, 3, 7),
    },
    {
        "vendor": "Asana",
        "description": "Asana Starter (5 seats, Mar 8-Apr 7)",
        "category": "software",
        "subtotal": Decimal("67.45"),
        "tax": Decimal("3.91"),
        "total": Decimal("71.36"),
        "payment_method": "paypal_bank",
        "reference": "INV INV05054314",
        "date": date(2026, 3, 8),
    },
    {
        "vendor": "TX Sec of State",
        "description": "Certificate of Assumed Business Name (DBA) — Nock Technologies",
        "category": "formation",
        "subtotal": Decimal("25.00"),
        "tax": Decimal("0.00"),
        "total": Decimal("25.00"),
        "payment_method": "card_c",
        "reference": "Batch 156558389",
        "date": date(2026, 3, 9),
    },
    {
        "vendor": "UpCounsel",
        "description": "Trademark Application and Conflict Assessment — NOCK filing",
        "category": "legal",
        "subtotal": Decimal("688.50"),
        "tax": Decimal("0.00"),
        "total": Decimal("688.50"),
        "payment_method": "card_c",
        "reference": "UpCounsel INV #00499",
        "date": date(2026, 3, 14),
    },
    {
        "vendor": "ZOHO Corporation",
        "description": "Zoho Workplace Mail Lite (2 users, yearly Mar 14 2026-Mar 13 2027)",
        "category": "software",
        "subtotal": Decimal("24.00"),
        "tax": Decimal("1.39"),
        "total": Decimal("25.39"),
        "payment_method": "paypal",
        "reference": "Zoho INV #50101760548",
        "date": date(2026, 3, 14),
    },
]


class Command(BaseCommand):
    help = "Seed real business expenses from Asana tracking (17 expenses)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing expenses before seeding.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["clear"]:
            deleted, _ = Expense.objects.all().delete()
            self.stdout.write(f"  Cleared {deleted} existing expenses.")

        created_count = 0
        for exp in EXPENSES:
            _, created = Expense.objects.get_or_create(
                vendor=exp["vendor"],
                date=exp["date"],
                reference=exp["reference"],
                defaults={
                    "description": exp["description"],
                    "category": exp["category"],
                    "subtotal": exp["subtotal"],
                    "tax": exp["tax"],
                    "total": exp["total"],
                    "is_refund": exp.get("is_refund", False),
                    "payment_method": exp["payment_method"],
                },
            )
            status = "created" if created else "exists"
            if created:
                created_count += 1
            self.stdout.write(f"  {exp['date']} {exp['vendor']}: ${exp['total']} — {status}")

        # Compute totals
        gross = sum(e["total"] for e in EXPENSES if not e.get("is_refund", False))
        refunds = sum(e["total"] for e in EXPENSES if e.get("is_refund", False))
        net = gross - refunds
        tax_total = sum(e["tax"] for e in EXPENSES if not e.get("is_refund", False))

        self.stdout.write("")
        self.stdout.write(f"  Gross:   ${gross}")
        self.stdout.write(f"  Refunds: -${refunds}")
        self.stdout.write(f"  Net:     ${net}")
        self.stdout.write(f"  Tax:     ${tax_total}")
        self.stdout.write(self.style.SUCCESS(f"\nDone. {created_count} expenses created."))
