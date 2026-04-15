from django.apps import AppConfig


class WorkspacesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workspaces"

    def ready(self) -> None:
        import workspaces.signals  # noqa: F401
