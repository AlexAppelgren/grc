"""The shared app: auth, permissions, tenancy, audit, vocabulary base, adapters, storage,
health, seeds and the structural guards (playbook 2.2)."""

from django.apps import AppConfig


class SharedConfig(AppConfig):
    name = "apps.shared"
    label = "shared"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Boot guard 7 of the production-safety block: refuse a database role that can
        # bypass row-level security (playbook 11.1, AC-NFR2). It opens the default
        # connection, which settings.py must not do, so it runs here.
        from apps.shared.db_role_guard import check_at_boot

        check_at_boot()
