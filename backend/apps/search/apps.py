from django.apps import AppConfig


class SearchConfig(AppConfig):
    name = "apps.search"
    label = "search"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # A library change that moved the index owes embeddings, filled on the ordered outbox
        # cursor (SRC-01). Registered here, never on import: nothing imports
        # `apps.search.tasks` in an API process, so an import-time registration would be absent.
        from apps.search import tasks

        tasks.register()
