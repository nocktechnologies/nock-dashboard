from django import forms

from .models import Contact, Deal, DealNote

_input = "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white"


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "company", "email", "phone", "role", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _input, "placeholder": "Full name"}),
            "company": forms.TextInput(attrs={"class": _input, "placeholder": "Company name"}),
            "email": forms.EmailInput(attrs={"class": _input, "placeholder": "email@example.com"}),
            "phone": forms.TextInput(attrs={"class": _input, "placeholder": "Phone number"}),
            "role": forms.TextInput(attrs={"class": _input, "placeholder": "Role / title"}),
            "notes": forms.Textarea(attrs={"class": _input, "rows": 3, "placeholder": "Notes"}),
        }


class DealForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            "title", "contact", "stage", "source", "estimated_value",
            "actual_value", "description", "next_action", "next_action_date",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": _input, "placeholder": "Deal title"}),
            "contact": forms.Select(attrs={"class": _input}),
            "stage": forms.Select(attrs={"class": _input}),
            "source": forms.Select(attrs={"class": _input}),
            "estimated_value": forms.NumberInput(attrs={
                "class": _input, "step": "0.01", "placeholder": "0.00",
            }),
            "actual_value": forms.NumberInput(attrs={
                "class": _input, "step": "0.01", "placeholder": "0.00",
            }),
            "description": forms.Textarea(attrs={"class": _input, "rows": 3}),
            "next_action": forms.TextInput(attrs={"class": _input, "placeholder": "Next step"}),
            "next_action_date": forms.DateInput(attrs={"class": _input, "type": "date"}),
        }


class DealNoteForm(forms.ModelForm):
    class Meta:
        model = DealNote
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={
                "class": _input, "rows": 2, "placeholder": "Add a note...",
            }),
        }
