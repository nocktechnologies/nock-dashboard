import mimetypes

from django import forms

from .models import Document


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "category", "file", "description", "tags"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "placeholder": "Document title",
            }),
            "category": forms.Select(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
            }),
            "file": forms.ClearableFileInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white file:mr-4 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-brand-500 file:text-white hover:file:bg-brand-500/80",
                "accept": ".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "rows": 3,
                "placeholder": "Description of this document",
            }),
            "tags": forms.TextInput(attrs={
                "class": "w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white",
                "placeholder": "Comma-separated tags",
            }),
        }

    def save(self, commit: bool = True) -> Document:
        instance = super().save(commit=False)
        if instance.file:
            instance.filename = instance.file.name
            instance.file_size = instance.file.size
            mime_type, _ = mimetypes.guess_type(instance.file.name)
            instance.file_type = mime_type or "application/octet-stream"
        if commit:
            instance.save()
        return instance
