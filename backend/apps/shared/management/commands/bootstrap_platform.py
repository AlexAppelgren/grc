"""`manage.py bootstrap_platform --admin-email <address> [--role <key>]`: the first platform
admin (ID-01, chunk 1 brief), and afterwards the library editors the owner names
(D-14, ADM-02, FIRST_RUN_SETUP step 13). Creates the user with the named platform role and
a platform invitation (tenant null), and prints the invitation link once: the emailed link
goes through the configured mailer as well, so on a deploy the mock is never involved.

Only a platform role can be granted here: a tenant role key or an unknown one is refused,
so the command can never hand a bank's role to platform staff. The grant and its
`platform_role.assigned` audit row land in the same transaction as the invitation.

Platform staff are separate accounts. Anyone a bank knows (a membership, active or
deactivated, or a bank invitation not accepted or revoked) is refused before anything is
written: a platform role on their account would reach into their bank session, and the
grant's audit row, which has no tenant, would never show in the bank's log. A second
platform role on an account that already holds one is refused too, unless --add-role asks
for it.

Idempotent per address: an existing user keeps their roles and gets a fresh invitation
unless they already hold a live passkey, in which case there is nothing to bootstrap. The
output names every platform role the account then holds."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.identity import invitation_logic, mail, roles_logic
from apps.identity.models import PlatformRole, PlatformRoleAssignment
from apps.shared.audit import Actor, record
from apps.shared.vocabulary import label_for

ACTOR_LABEL = "bootstrap_platform"


class Command(BaseCommand):
    help = (
        "Create a platform administrator or library editor and their enrolment invitation. "
        "Platform staff are separate accounts: an address a bank knows is refused."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--admin-email", required=True, help="The address to invite; never one a bank knows.")
        parser.add_argument(
            "--role",
            default="platform_admin",
            help="The platform role to grant: platform_admin (the default) or library_editor.",
        )
        parser.add_argument(
            "--add-role",
            action="store_true",
            help="Grant the role to an account that already holds a different platform role.",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        email = invitation_logic.normalise_email(str(options["admin_email"]))
        role_key = str(options["role"]).strip().lower()
        with transaction.atomic():
            roles_logic.ensure_platform_roles()
            try:
                role = PlatformRole.objects.get(key=role_key)
            except PlatformRole.DoesNotExist:
                known = ", ".join(PlatformRole.objects.order_by("key").values_list("key", flat=True))
                raise CommandError(f"{role_key} is not a platform role. Pick one of: {known}.") from None
            user = invitation_logic.get_or_create_user(email)
            if invitation_logic.belongs_to_a_tenant(user):
                raise CommandError(
                    f"{user.name} belongs to a bank. Platform staff are separate accounts: use an address of their own."
                )
            if invitation_logic.has_live_passkey(user):
                raise CommandError(f"{user.name} already holds a passkey; nothing to bootstrap.")
            held = set(PlatformRoleAssignment.objects.filter(user=user).values_list("role__key", flat=True))
            if held - {role.key} and not options["add_role"]:
                raise CommandError(
                    f"{user.name} already holds {', '.join(sorted(held))}. Pass --add-role to grant {role.key} as well."
                )
            title = label_for(role, [roles_logic.DEFAULT_LANGUAGE])
            _, granted = PlatformRoleAssignment.objects.get_or_create(user=user, role=role)
            if granted:
                record(
                    action="platform_role.assigned",
                    actor=Actor.system(ACTOR_LABEL),
                    subject_type="user",
                    subject_id=user.id,
                    subject_title=user.name,
                    summary=f"Platform role {role.key} granted by {ACTOR_LABEL}.",
                    tenant_id=None,
                    after={"userId": str(user.id), "role": role.key},
                )
            issued = invitation_logic.create_invitation(
                tenant=None,
                email=email,
                roles=[],
                title=title,
                invited_by=None,
                actor=Actor.system(ACTOR_LABEL),
            )
        self.stdout.write(f"{title.lower()} {user.name} ({user.id}) invited")
        self.stdout.write(f"platform roles: {', '.join(sorted(held | {role.key}))}")
        self.stdout.write(f"invitation link (valid once): {mail.invitation_link(issued.token)}")
