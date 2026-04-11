from decimal import Decimal

from django.db import models


class Contact(models.Model):
    name = models.CharField(max_length=200)
    company = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        if self.company:
            return f"{self.name} ({self.company})"
        return self.name


class Deal(models.Model):
    STAGES = [
        ("prospect", "Prospect"),
        ("contacted", "Contacted"),
        ("proposal", "Proposal Sent"),
        ("negotiation", "Negotiation"),
        ("active", "Active Engagement"),
        ("closed_won", "Closed Won"),
        ("closed_lost", "Closed Lost"),
    ]
    SOURCES = [
        ("consulting", "Nock Consulting"),
        ("academy", "Nock Academy"),
        ("licensing", "Nexus Licensing"),
        ("referral", "Referral"),
        ("inbound", "Inbound"),
        ("other", "Other"),
    ]

    title = models.CharField(max_length=200)
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="deals"
    )
    stage = models.CharField(max_length=20, choices=STAGES, default="prospect")
    source = models.CharField(max_length=20, choices=SOURCES)
    estimated_value = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    actual_value = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    description = models.TextField(blank=True)
    next_action = models.CharField(max_length=200, blank=True)
    next_action_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def display_value(self) -> Decimal | None:
        return self.actual_value if self.actual_value is not None else self.estimated_value

    @property
    def is_open(self) -> bool:
        return self.stage not in ("closed_won", "closed_lost")


class DealNote(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="deal_notes")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Note on {self.deal.title} — {self.created_at:%Y-%m-%d}"
