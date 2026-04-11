from django.contrib import admin

from .models import Contact, Deal, DealNote


class DealNoteInline(admin.TabularInline):
    model = DealNote
    extra = 0


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "email", "phone", "created_at")
    search_fields = ("name", "company", "email")
    ordering = ("name",)


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "contact", "stage", "source", "estimated_value", "updated_at")
    list_filter = ("stage", "source")
    search_fields = ("title", "description")
    ordering = ("-updated_at",)
    inlines = [DealNoteInline]
