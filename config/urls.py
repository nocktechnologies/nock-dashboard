from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views
from brain import views_handoffs, views_research
from brain import views as brain_views
from crm.views import contacts_api, deals_api
from intelligence import views as intelligence_views
from remote import views as remote_views
from sessions import views as sessions_views
from teams import views as teams_views
from vault import views as vault_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls", namespace="dashboard")),
    path("", include("pipeline.urls", namespace="pipeline")),
    path("", include("tasks.urls", namespace="tasks")),
    path("api/tasks/", include("tasks.api_urls", namespace="tasks_api")),
    # Projects plugin (standalone reusable PM API, `projects/` app).
    # Mounted under `/api/pm/` because the plugin's internal urlpatterns
    # use `api/tasks/*`, `api/projects/*`, `api/sections/*`, `api/comments/*`
    # routes that would otherwise collide with `tasks.api_urls` above (which
    # owns `/api/tasks/*` for the Asana write-back API). The prefix keeps
    # the plugin standalone — nothing changes inside `projects/urls.py`.
    # Final routes land under `/api/pm/api/projects/`, `/api/pm/api/tasks/`,
    # `/api/pm/api/sections/`, `/api/pm/api/comments/`.
    path("api/pm/", include("projects.urls")),
    path("", include("sessions.urls", namespace="sessions")),
    path("context/", include("context.urls", namespace="context")),
    path("spend/", include("spend.urls", namespace="spend")),
    path("notifications/", include("notifications.urls", namespace="notifications")),
    # /accounts/profile/ is a direct path (not via include) so it
    # resolves BEFORE allauth's broad include below catches everything
    # else under /accounts/. PR 3 will add more direct paths here as
    # the UserProfile model, billing management, and team-invite views land.
    path("accounts/profile/", accounts_views.profile_view, name="account-profile"),
    # All auth flows (login, signup, logout, password reset, email verify)
    # owned by django-allauth.
    path("accounts/", include("allauth.urls")),
    path("remote/", include("remote.urls", namespace="remote")),
    path("vault/", include("vault.urls", namespace="vault")),
    path("crm/", include("crm.urls", namespace="crm")),
    path("intelligence/", include("intelligence.urls", namespace="intelligence")),
    path("brain/", include("brain.urls", namespace="brain")),
    path("", include("teams.urls", namespace="teams")),
    # Mobile API — Teams endpoints at /api/teams/
    path("api/teams/", teams_views.teams_list_create, name="teams-api"),
    path("api/teams/active/", teams_views.active_teams, name="teams-active-api"),
    path("api/teams/<int:team_id>/", teams_views.team_detail, name="teams-detail-api"),
    path("api/teams/<int:team_id>/members/", teams_views.members_list_create, name="teams-members-api"),
    path("api/teams/<int:team_id>/members/<int:member_id>/", teams_views.member_detail, name="teams-member-detail-api"),
    path("api/teams/<int:team_id>/tasks/", teams_views.tasks_list_create, name="teams-tasks-api"),
    path("api/teams/<int:team_id>/tasks/<int:task_id>/", teams_views.task_detail, name="teams-task-detail-api"),
    path("api/teams/<int:team_id>/tasks/<int:task_id>/start/", teams_views.task_start, name="teams-task-start-api"),
    path("api/teams/<int:team_id>/tasks/<int:task_id>/complete/", teams_views.task_complete, name="teams-task-complete-api"),
    path("api/teams/<int:team_id>/events/", teams_views.events_list, name="teams-events-api"),
    # Mobile API — Prompt Queue endpoints at /api/prompts/
    path("api/prompts/", teams_views.prompts_list_create, name="prompts-api"),
    path("api/prompts/queue/", teams_views.prompt_queue, name="prompts-queue-api"),
    path("api/prompts/ready-for-kevin/", teams_views.prompts_ready_for_kevin, name="prompts-ready-api"),
    path("api/prompts/stats/", teams_views.prompt_stats, name="prompts-stats-api"),
    path("api/prompts/<slug:slug>/", teams_views.prompt_detail, name="prompts-detail-api"),
    path("api/prompts/<slug:slug>/execute/", teams_views.prompt_execute, name="prompts-execute-api"),
    path("api/prompts/<slug:slug>/complete/", teams_views.prompt_complete, name="prompts-complete-api"),
    path("api/prompts/<slug:slug>/review/", teams_views.prompt_review, name="prompts-review-api"),
    # Mobile API — CRM endpoints at /api/crm/
    path("api/crm/deals/", deals_api, name="crm-deals-api"),
    path("api/crm/contacts/", contacts_api, name="crm-contacts-api"),
    # Mobile API — Intelligence endpoints at /api/intelligence/
    path("api/intelligence/alerts/", intelligence_views.alerts_api, name="intelligence-alerts-api"),
    path("api/intelligence/advisor/chat/", intelligence_views.advisor_chat_api, name="intelligence-advisor-chat-api"),
    path("api/intelligence/advisor/conversations/", intelligence_views.conversations_list_api, name="intelligence-conversations-api"),
    path("api/intelligence/advisor/conversations/<int:pk>/", intelligence_views.conversation_detail_api, name="intelligence-conversation-detail-api"),
    path("api/intelligence/snapshot/latest/", intelligence_views.snapshot_latest_api, name="intelligence-snapshot-api"),
    path("api/intelligence/memo/generate/", intelligence_views.memo_generate_api, name="intelligence-memo-api"),
    path("api/intelligence/smart-watch/status/", intelligence_views.smart_watch_status, name="intelligence-smart-watch-status-api"),
    path("api/intelligence/smart-watch/rules/", intelligence_views.smart_watch_rules_list, name="intelligence-smart-watch-rules-api"),
    path("api/intelligence/smart-watch/events/", intelligence_views.smart_watch_events_list, name="intelligence-smart-watch-events-api"),
    # Mobile API — Remote endpoints at /api/remote/
    path("api/remote/commands/", remote_views.command_list_create, name="remote-commands-api"),
    path("api/remote/commands/<int:command_id>/", remote_views.command_detail, name="remote-command-detail-api"),
    path("api/remote/commands/<int:command_id>/cancel/", remote_views.command_cancel, name="remote-command-cancel-api"),
    path("api/remote/agent/status/", remote_views.agent_status, name="remote-agent-status-api"),
    path("api/remote/output/<str:session_id>/", remote_views.session_output, name="remote-output-api"),
    path("api/remote/stream/<str:session_id>/", remote_views.stream_output, name="remote-stream-api"),
    path("api/remote/kill-all/", remote_views.kill_all, name="remote-kill-all-api"),
    path("api/remote/conversations/", remote_views.conversation_list_create, name="remote-conversations-api"),
    path("api/remote/conversations/<int:conversation_id>/", remote_views.conversation_detail, name="remote-conversation-detail-api"),
    path("api/remote/conversations/<int:conversation_id>/send/", remote_views.conversation_send, name="remote-conversation-send-api"),
    # Mobile API — Brain endpoints at /api/brain/
    path("api/brain/entries/", brain_views.entries_list_create, name="brain-entries-api"),
    path("api/brain/entries/<int:entry_id>/", brain_views.entry_detail, name="brain-entry-detail-api"),
    path("api/brain/categories/", brain_views.categories_list, name="brain-categories-api"),
    path("api/brain/brief/", brain_views.generate_brief, name="brain-brief-api"),
    path("api/brain/stats/", brain_views.stats, name="brain-stats-api"),
    path("api/brain/consolidate/", brain_views.consolidate, name="brain-consolidate-api"),
    path("api/brain/consolidation-history/", brain_views.consolidation_history, name="brain-consolidation-history-api"),
    path("api/brain/morning-note/test/", brain_views.send_test_morning_note, name="brain-morning-note-test-api"),
    # Session Handoffs API — operational state per context
    path("api/brain/handoffs/", views_handoffs.handoffs_list, name="brain-handoffs-api"),
    path("api/brain/handoffs/latest/", views_handoffs.handoffs_latest, name="brain-handoffs-latest-api"),
    path("api/brain/handoffs/<str:context>/", views_handoffs.handoff_detail, name="brain-handoff-detail-api"),
    path("api/brain/handoffs/<str:context>/history/", views_handoffs.handoff_history, name="brain-handoff-history-api"),
    # Research Library API — semantic search over the user's knowledge corpus
    path("api/brain/research/search/", views_research.research_search, name="brain-research-search-api"),
    path("api/brain/research/documents/", views_research.research_documents_list, name="brain-research-docs-api"),
    path("api/brain/research/documents/<slug:slug>/", views_research.research_document_detail, name="brain-research-doc-detail-api"),
    path("api/brain/research/topics/", views_research.research_topics, name="brain-research-topics-api"),
    path("api/brain/research/stats/", views_research.research_stats, name="brain-research-stats-api"),
    # Mobile API — Terminal Bridge endpoints at /api/terminal/
    path("api/terminal/heartbeat/", sessions_views.terminal_heartbeat, name="terminal-heartbeat-api"),
    path("api/terminal/status/", sessions_views.terminal_status, name="terminal-status-api"),
    path("api/terminal/reports/", vault_views.session_reports_api, name="terminal-reports-api"),
    path("api/terminal/reports/<int:pk>/", vault_views.session_report_detail_api, name="terminal-report-detail-api"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
