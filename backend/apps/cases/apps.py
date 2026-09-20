from django.apps import AppConfig


class CasesConfig(AppConfig):
    name = "apps.cases"
    label = "cases"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # A registered change opens one case per bank, on the one ordered cursor over
        # outbox_event (CAS-01, chunk 5 ruling 32). The handler is registered here because
        # this is where the app is ready and the model registry is loaded.
        from apps.cases import creation

        creation.register()
