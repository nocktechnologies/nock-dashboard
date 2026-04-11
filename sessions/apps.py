from django.apps import AppConfig


class AgentSessionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sessions"
    label = "agent_sessions"
