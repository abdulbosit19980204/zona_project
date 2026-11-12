from django.apps import AppConfig


class ZonaConfig(AppConfig):
    name = "zona"
    label = "zona"
    verbose_name = "Responsibility Architecture"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401 — WebSocket tarqatish signallari
