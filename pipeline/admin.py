from django.contrib import admin

from .models import Branch, BranchEvent, PipelineEvent, PREvent, PullRequest, Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ["__str__", "github_id", "default_branch", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "owner"]
    readonly_fields = ["created_at"]


class PREventInline(admin.TabularInline):
    model = PREvent
    extra = 0
    readonly_fields = ["event_type", "actor", "payload", "created_at"]
    can_delete = False


@admin.register(PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "state",
        "ci_status",
        "coderabbit_status",
        "author",
        "generating_agent",
        "opened_at",
    ]
    list_filter = ["state", "ci_status", "coderabbit_status", "repository"]
    search_fields = ["title", "author", "branch"]
    readonly_fields = ["last_updated"]
    inlines = [PREventInline]


@admin.register(PREvent)
class PREventAdmin(admin.ModelAdmin):
    list_display = ["__str__", "event_type", "actor", "created_at"]
    list_filter = ["event_type"]
    search_fields = ["actor", "event_type"]
    readonly_fields = ["created_at"]


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["__str__", "last_commit_sha", "last_commit_at", "is_active"]
    list_filter = ["is_active", "repository"]
    search_fields = ["name"]


@admin.register(BranchEvent)
class BranchEventAdmin(admin.ModelAdmin):
    list_display = ["__str__", "delivery_id", "deleted", "created_at"]
    list_filter = ["deleted", "repository"]
    search_fields = ["delivery_id", "ref"]
    readonly_fields = ["created_at"]


@admin.register(PipelineEvent)
class PipelineEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "severity", "category", "repo", "title", "agent", "lane"]
    list_filter = ["severity", "category", "repo", "agent", "lane"]
    search_fields = ["title", "details", "workflow_id"]
    readonly_fields = ["id", "created_at"]
    ordering = ["-created_at"]
