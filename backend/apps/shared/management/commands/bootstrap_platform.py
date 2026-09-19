"""`manage.py bootstrap_platform --admin-email <address>`: the first platform admin (ID-01,
chunk 1 brief). Creates the user with the `platform_admin` role and a platform
invitation (tenant null), and prints the invitation link once: the emailed link goes
through the configured mailer as well, so on a deploy the mock is never involved.

Idempotent per address: an existing user keeps their roles and gets a fresh invitation
unless they already hold a live passkey, in which case there is nothing to bootstrap."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.identity import invitation_logic, mail, roles_logic
from apps.identity.models import PlatformRole, PlatformRoleAssignment
from apps.shared.audit import Actor


class Command(BaseCommand):
    help = "Create the platform administrator and their enrolment invitation."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--admin-email", required=True, help="The platform administrator's address.")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        email = invitation_logic.normalise_email(str(options["admin_email"]))
        with transaction.atomic():
            roles_logic.ensure_platform_roles()
            user = invitation_logic.get_or_create_user(email)
            if invitation_logic.has_live_passkey(user):
                raise CommandError(f"{user.name} already holds a passkey; nothing to bootstrap.")
            role = PlatformRole.objects.get(key="platform_admin")
            PlatformRoleAssignment.objects.get_or_create(user=user, role=role)
            issued = invitation_logic.create_invitation(
                tenant=None,
                email=email,
                roles=[],
                title="Platform administrator",
                invited_by=None,
                actor=Actor.system("bootstrap_platform"),
            )
        self.stdout.write(f"platform administrator {user.name} ({user.id}) invited")
        self.stdout.write(f"invitation link (valid once): {mail.invitation_link(issued.token)}")
