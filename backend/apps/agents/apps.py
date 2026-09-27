from django.apps import AppConfig


class AgentsConfig(AppConfig):
    name = "apps.agents"
    label = "agents"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # An approved scope item opens research by the bank's own agent, on the one ordered
        # cursor over outbox_event (OWN-02, d89-agent-research).
        from apps.agents import scope_research

        scope_research.register()
