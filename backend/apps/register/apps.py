from django.apps import AppConfig


class RegisterConfig(AppConfig):
    name = "apps.register"
    label = "register"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # `RegisterPanels` names the watch app's change page, whose module imports the
        # library's schemas, which import this app's: it resolves here, once every app loaded.
        from apps.register import schemas
        from apps.watch.schemas import WatchObligationChangePage

        schemas.RegisterPanels.model_rebuild(_types_namespace={"WatchObligationChangePage": WatchObligationChangePage})
        schemas.RegisterEntryWithPanels.model_rebuild()
