from django.apps import AppConfig


class AgentsConfig(AppConfig):
    name = "apps.agents"
    label = "agents"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # An approved scope item opens research by the bank's own agent, on the ordered outbox
        # cursor (OWN-02).
        from apps.agents import scope_research

        scope_research.register()
