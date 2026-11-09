from django.apps import AppConfig


class ProposalsConfig(AppConfig):
    name = "apps.proposals"
    label = "proposals"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # An approved library instrument queues the baseline filing, so its duties follow
        # within seconds (D-118). Registered here, never on import: nothing imports
        # `apps.proposals.tasks` in a running API process.
        from apps.proposals import tasks

        tasks.register()
