from django.apps import AppConfig


class CasesConfig(AppConfig):
    name = "apps.cases"
    label = "cases"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # A registered change opens one case per bank, on the one ordered cursor over
        # outbox_event (CAS-01, chunk 5 ruling 32). The handler is registered here because
        # this is where the app is ready and the model registry is loaded.
        from apps.cases import creation, matching, so_what

        creation.register()
        # A run's drafted "So what?" reaches every bank whose copy is still that draft, on
        # the same cursor (WAT-05, D-66).
        so_what.register()
        # The footprint verdict a case caches goes stale when the bank's scope or the
        # change's scope terms move; both are re-decided on the same cursor (FP-03).
        matching.register()
