from decimal import Decimal

from django import forms

from .models import Expense, Revenue


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "vendor",
            "description",
            "category",
            "subtotal",
            "tax",
            "total",
            "is_refund",
            "payment_method",
            "date",
            "reference",
            "receipt",
            "notes",
        ]
        widgets = {
            "vendor": forms.TextInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "placeholder": "e.g. Anthropic",
                "autocomplete": "off",
                "list": "vendor-suggestions",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "rows": 2,
                "placeholder": "What was this expense for?",
            }),
            "category": forms.Select(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
            }),
            "subtotal": forms.NumberInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "step": "0.01",
                "min": "0",
                "placeholder": "0.00",
            }),
            "tax": forms.NumberInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "step": "0.01",
                "min": "0",
                "placeholder": "0.00",
            }),
            "total": forms.NumberInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "step": "0.01",
                "min": "0",
                "placeholder": "Auto-calc",
            }),
            "payment_method": forms.Select(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
            }),
            "date": forms.DateInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "type": "date",
            }),
            "reference": forms.TextInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "placeholder": "Invoice number or reference",
            }),
            "receipt": forms.ClearableFileInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white file:mr-4 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-brand-500 file:text-white hover:file:bg-brand-500/80",
                "accept": "image/*,.pdf",
            }),
            "notes": forms.Textarea(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "rows": 2,
                "placeholder": "Optional notes",
            }),
            "is_refund": forms.CheckboxInput(attrs={
                "class": "rounded bg-gray-800 border-gray-700 text-brand-500 focus:ring-brand-500",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["total"].required = False

    def clean(self) -> dict:
        cleaned = super().clean()
        subtotal = cleaned.get("subtotal") or Decimal("0")
        tax = cleaned.get("tax") or Decimal("0")
        total = cleaned.get("total")
        if not total:
            cleaned["total"] = subtotal + tax
        return cleaned

    def save(self, commit: bool = True) -> Expense:
        instance = super().save(commit=False)
        if instance.receipt:
            instance.receipt_filename = instance.receipt.name
        if commit:
            instance.save()
        return instance


class RevenueForm(forms.ModelForm):
    class Meta:
        model = Revenue
        fields = [
            "source",
            "description",
            "amount",
            "client",
            "date",
            "reference",
            "notes",
        ]
        widgets = {
            "source": forms.Select(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "rows": 2,
                "placeholder": "Description of revenue",
            }),
            "amount": forms.NumberInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "step": "0.01",
                "min": "0",
                "placeholder": "0.00",
            }),
            "client": forms.TextInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "placeholder": "Client name",
            }),
            "date": forms.DateInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "type": "date",
            }),
            "reference": forms.TextInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "placeholder": "Invoice or reference number",
            }),
            "notes": forms.Textarea(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "rows": 2,
                "placeholder": "Optional notes",
            }),
        }
