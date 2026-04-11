from decimal import Decimal

from django.core.validators import FileExtensionValidator
from django.db import models


class UsagePeriod(models.Model):
    date = models.DateField()
    model = models.CharField(max_length=100)
    workspace = models.CharField(max_length=255, blank=True)
    input_tokens = models.BigIntegerField(default=0)
    output_tokens = models.BigIntegerField(default=0)
    cache_read_tokens = models.BigIntegerField(default=0)
    cache_write_tokens = models.BigIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("0"))
    request_count = models.IntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "model"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "model", "workspace"],
                name="unique_usage_period_date_model_workspace",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date} — {self.model}: ${self.cost_usd}"


class SpendBudget(models.Model):
    month = models.DateField(unique=True)
    budget_usd = models.DecimalField(max_digits=10, decimal_places=2)
    alert_threshold_pct = models.IntegerField(default=80)
    alert_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month"]

    def __str__(self) -> str:
        return f"{self.month} — ${self.budget_usd} budget"


class SubscriptionTracker(models.Model):
    PROVIDER_CHOICES = [
        ("anthropic", "Anthropic"),
        ("openai", "OpenAI"),
        ("google", "Google"),
        ("github", "GitHub"),
        ("vercel", "Vercel"),
        ("coderabbit", "CodeRabbit"),
        ("asana", "Asana"),
        ("moonshot", "Moonshot AI"),
        ("zoho", "ZOHO"),
        ("railway", "Railway"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    monthly_cost = models.DecimalField(max_digits=8, decimal_places=2)
    renewal_date = models.DateField()
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self) -> str:
        return f"{self.name} — ${self.monthly_cost}/mo"


class Expense(models.Model):
    CATEGORIES = [
        ("software", "Software & Dev Tools"),
        ("hardware", "Hardware"),
        ("infrastructure", "Infrastructure"),
        ("domains", "Domains & Branding"),
        ("formation", "Business Formation"),
        ("legal", "Legal & Professional"),
        ("other", "Other"),
    ]
    PAYMENT_METHODS = [
        ("amex_1009", "Amex -1009 (Delta SkyMiles)"),
        ("visa_5540", "Visa -5540"),
        ("amex_8515", "Amex -8515"),
        ("stripe_link", "Link (Stripe)"),
        ("paypal_cap1", "PayPal → Capital One ••2250"),
        ("paypal", "PayPal (kkwills13@gmail.com)"),
        ("other", "Other"),
    ]

    vendor = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORIES)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=10, decimal_places=2)
    is_refund = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference = models.CharField(max_length=200, blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    receipt = models.FileField(
        upload_to="receipts/",
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "png", "jpg", "jpeg"])],
    )
    receipt_filename = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date", "vendor"]

    def __str__(self) -> str:
        prefix = "REFUND " if self.is_refund else ""
        return f"{prefix}{self.date} — {self.vendor}: ${self.total}"


class Revenue(models.Model):
    SOURCES = [
        ("consulting", "Nock Consulting"),
        ("academy", "Nock Academy (Gumroad)"),
        ("licensing", "Nexus Licensing"),
        ("other", "Other"),
    ]

    source = models.CharField(max_length=20, choices=SOURCES)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    client = models.CharField(max_length=200, blank=True)
    date = models.DateField()
    reference = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "source"]

    def __str__(self) -> str:
        return f"{self.date} — {self.get_source_display()}: ${self.amount}"
