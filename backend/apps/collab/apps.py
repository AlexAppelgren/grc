from django.apps import AppConfig


class CollabConfig(AppConfig):
    name = "apps.collab"
    label = "collab"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # A confirmed link and a new version tell the people involved in the obligation at
        # every bank, on the one ordered cursor over outbox_event (COL-02, D-25, D-97).
        from apps.collab import producers

        producers.register()
