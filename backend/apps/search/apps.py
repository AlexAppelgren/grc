from django.apps import AppConfig


class SearchConfig(AppConfig):
    name = "apps.search"
    label = "search"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # A library change that moved the index owes embeddings, filled on the one ordered
        # cursor over outbox_event (SRC-01, ruling 9). The handler is registered here
        # because this is where the app is ready and the model registry is loaded, and
        # never at import time: nothing imports `apps.search.tasks` in a running API
        # process, so a registration on import would be absent where the write happens.
        from apps.search import tasks

        tasks.register()
