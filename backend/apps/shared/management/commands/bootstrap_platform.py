"""`manage.py bootstrap_platform --admin-email <address> --role <key>`: the first platform
admin (ID-01, chunk 1 brief), and afterwards the library editors the owner names
(D-14, ADM-02, FIRST_RUN_SETUP step 13). Creates the user with the named platform role and
a platform invitation (tenant null), and prints the invitation link once: the emailed link
goes through the configured mailer as well, so on a deploy the mock is never involved.

Exactly one of `--role`, `--revoke-role` and `--reenrol` is given: no role is granted by
default (review 2026-11-11 S-15). Only a platform role can be granted here: a tenant role key
or an unknown one is refused, so the command can never hand a bank's role to platform staff.
The grant and its `platform_role.assigned` audit row land in the same transaction as the
invitation. Before anything is granted to, or revoked from, an account that already exists,
the command prints that account (name, address, id, status, banks and platform roles) and
asks for confirmation; `--yes` gives it non-interactively, and without a terminal and
without `--yes` nothing is written.

A bank's member may be platform staff too (D-122, ADR 0067): each of their sessions holds
one zone's grants only, and they switch with a passkey. The bank sees the grant: the
`platform_role.assigned` row is written in each bank they are an active member of as well
as without a tenant. A member who already holds a live passkey needs no invitation and gets
none; they switch to the console from the account menu. A second platform role on an
account that already holds one is refused, unless --add-role asks for it.

Idempotent per address: an existing user keeps their roles and gets a fresh invitation
unless they already hold a live passkey, in which case a run that grants nothing new is
refused, since there is nothing to bootstrap. The output names every platform role the
account then holds.

`--revoke-role <key>` removes one platform role, with a `platform_role.revoked` audit row
without a tenant and in each bank the person is an active member of; when it was their last
platform role, their console sessions end.

`--reenrol` is ID-05's recovery for an account no bank may re-enrol on its own: platform
staff, and a member of more than one bank (review 2026-11-11 S-2). Every session revoked,
every passkey retired (a lost device, or passkeys made under an RP ID the deployment no
longer uses), every personal access token revoked, and a re-enrolment invitation sent. The
account keeps its roles and memberships. Its passkeys open its banks too, so its sessions
and tokens there are revoked as well, and each bank's audit log records the re-enrolment."""

from __future__ import annotations

import sys
import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.identity import api_keys_logic, invitation_logic, mail, roles_logic, session_logic
from apps.identity.models import (
    InvitationKind,
    LoginEventKind,
    LoginMethod,
    PlatformRole,
    PlatformRoleAssignment,
    User,
    UserStatus,
    WebAuthnCredential,
)
from apps.identity.security_log import log_event
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.vocabulary import label_for

ACTOR_LABEL = "bootstrap_platform"


class Command(BaseCommand):
    help = (
        "Grant or revoke a platform role (platform_admin or library_editor), with an enrolment invitation "
        "for a new account, or re-enrol platform staff. A bank's member may be one too; each of their banks "
        "gets an audit row."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--admin-email", required=True, help="The address to invite, grant or revoke the role for.")
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--role", help="The platform role to grant: platform_admin or library_editor.")
        action.add_argument("--revoke-role", help="The platform role to take away from the account.")
        action.add_argument(
            "--reenrol",
            action="store_true",
            help="Retire the account's passkeys, revoke its sessions and personal tokens and send a re-enrolment link; its roles stay.",
        )
        parser.add_argument(
            "--add-role",
            action="store_true",
            help="Grant the role to an account that already holds a different platform role.",
        )
        parser.add_argument("--yes", action="store_true", help="Confirm a grant or revocation on an existing account without asking.")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        email = invitation_logic.normalise_email(str(options["admin_email"]))
        if options["reenrol"]:
            self._reenrol(email)
        elif options["revoke_role"] is not None:
            self._revoke(email, str(options["revoke_role"]).strip().lower(), yes=bool(options["yes"]))
        else:
            self._grant(email, str(options["role"]).strip().lower(), add_role=bool(options["add_role"]), yes=bool(options["yes"]))

    # -----------------------------------------------------------------------------------
    def _confirm(self, user: User, question: str, *, yes: bool) -> None:
        """Print the account the address resolved to, then ask, unless `--yes` answered."""
        banks = ", ".join(name for _, name in session_logic.held_banks(user)) or "none"
        roles = ", ".join(sorted(PlatformRoleAssignment.objects.filter(user=user).values_list("role__key", flat=True))) or "none"
        self.stdout.write(f"account: {user.name} <{user.email}> ({user.id}), {user.status}; banks: {banks}; platform roles: {roles}")
        if yes:
            return
        if not sys.stdin.isatty():
            raise CommandError("Nothing changed. Run it in a terminal to confirm, or pass --yes.")
        if input(f"{question} [y/N] ").strip().lower() not in ("y", "yes"):
            raise CommandError("Nothing changed.")

    def _role(self, key: str) -> PlatformRole:
        roles_logic.ensure_platform_roles()
        role = PlatformRole.objects.filter(key=key).first()  # ordering: key is unique, at most one row
        if role is None:
            known = ", ".join(PlatformRole.objects.order_by("key").values_list("key", flat=True))
            raise CommandError(f"{key} is not a platform role. Pick one of: {known}.")
        return role

    def _audit_everywhere(self, user: User, *, action: str, summary: str, after: dict[str, Any]) -> None:
        """The row without a tenant, then one in each bank the person is an active member of,
        last, as each one activates its bank (D-122)."""

        def write(tenant_id: uuid.UUID | None) -> None:
            record(
                action=action,
                actor=Actor.system(ACTOR_LABEL),
                subject_type="user",
                subject_id=user.id,
                subject_title=user.name,
                summary=summary,
                tenant_id=tenant_id,
                after=after,
            )

        write(None)
        for bank_id, _ in session_logic.held_banks(user):
            tenancy.activate(bank_id)
            write(bank_id)

    # -----------------------------------------------------------------------------------
    def _grant(self, email: str, role_key: str, *, add_role: bool, yes: bool) -> None:
        issued = None
        with transaction.atomic():
            role = self._role(role_key)
            existing = User.objects.filter(email=email).first()  # ordering: email is unique, at most one row
            user = existing or invitation_logic.get_or_create_user(email)
            held = set(PlatformRoleAssignment.objects.filter(user=user).values_list("role__key", flat=True))
            enrolled = invitation_logic.has_live_passkey(user)
            if enrolled and role.key in held:
                raise CommandError(f"{user.name} already holds a passkey; nothing to bootstrap.")
            if held - {role.key} and not add_role:
                raise CommandError(f"{user.name} already holds {', '.join(sorted(held))}. Pass --add-role to grant {role.key} as well.")
            if existing is not None and role.key not in held:
                self._confirm(user, f"Grant {role.key} to this account?", yes=yes)
            title = label_for(role, [roles_logic.DEFAULT_LANGUAGE])
            _, granted = PlatformRoleAssignment.objects.get_or_create(user=user, role=role)
            if not enrolled:
                issued = invitation_logic.create_invitation(
                    tenant=None, email=email, roles=[], title=title, invited_by=None, actor=Actor.system(ACTOR_LABEL)
                )
            if granted:
                self._audit_everywhere(
                    user,
                    action="platform_role.assigned",
                    summary=f"Platform role {role.key} granted by {ACTOR_LABEL}.",
                    after={"userId": str(user.id), "role": role.key},
                )
        self.stdout.write(f"{title.lower()} {user.name} ({user.id}) {'invited' if issued else 'granted'}")
        self.stdout.write(f"platform roles: {', '.join(sorted(held | {role.key}))}")
        if issued is None:
            self.stdout.write("already enrolled: no invitation sent; they switch to the console from the account menu")
        else:
            self.stdout.write(f"invitation link (valid once): {mail.invitation_link(issued.token)}")

    def _revoke(self, email: str, role_key: str, *, yes: bool) -> None:
        with transaction.atomic():
            role = self._role(role_key)
            user = User.objects.filter(email=email).first()  # ordering: email is unique, at most one row
            assignment = PlatformRoleAssignment.objects.filter(user=user, role=role).first() if user is not None else None  # ordering: unique (user, role)
            if user is None or assignment is None:
                raise CommandError(f"{email} does not hold {role.key}; nothing to revoke.")
            self._confirm(user, f"Revoke {role.key} from this account?", yes=yes)
            assignment.delete()
            left = sorted(PlatformRoleAssignment.objects.filter(user=user).values_list("role__key", flat=True))
            ended = 0
            if not left:
                # No platform role left: the console sessions hold nothing and end now. The
                # shell stands in no bank, the zone those sessions live in.
                ended = session_logic.revoke_all(user, tenant_id=None, reason="platform_role_revoked", actor=Actor.system(ACTOR_LABEL))
            self._audit_everywhere(
                user,
                action="platform_role.revoked",
                summary=f"Platform role {role.key} revoked by {ACTOR_LABEL}.",
                after={"userId": str(user.id), "role": role.key, "consoleSessionsRevoked": ended},
            )
        self.stdout.write(f"{user.name} ({user.id}) no longer holds {role.key}")
        self.stdout.write(f"platform roles: {', '.join(left) or 'none'}")

    def _reenrol(self, email: str) -> None:
        actor = Actor.system(ACTOR_LABEL)
        with transaction.atomic():
            user = User.objects.filter(email=email).first()  # ordering: email is unique, at most one row
            assignments = (
                list(PlatformRoleAssignment.objects.filter(user=user).select_related("role").order_by("role__key"))
                if user is not None
                else []
            )
            banks = session_logic.held_banks(user) if user is not None else []
            if user is None or (not assignments and len(banks) < 2):
                raise CommandError(
                    f"{email} holds no platform role and is a member of at most one bank; that bank re-issues their enrolment."
                )
            now = timezone.now()
            revoked = session_logic.revoke_all(user, tenant_id=None, reason="reenrolment", actor=actor)
            retired = WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).update(retired_at=now)
            user.status = UserStatus.INVITED.value
            user.save(update_fields=["status"])
            issued = invitation_logic.create_invitation(
                tenant=None,
                email=email,
                roles=[],
                title=label_for(assignments[0].role, [roles_logic.DEFAULT_LANGUAGE]) if assignments else "",
                invited_by=None,
                actor=actor,
                kind=InvitationKind.REENROLMENT,
            )
            log_event(
                event=LoginEventKind.REENROLMENT_ISSUED,
                method=LoginMethod.EMAIL_CODE,
                success=True,
                request=None,
                user=user,
                tenant_id=None,
                failure_reason="",
            )
            record(
                action="platform_staff.enrolment_reissued",
                actor=actor,
                subject_type="user",
                subject_id=user.id,
                subject_title=user.name,
                summary=f"Enrolment re-issued by {ACTOR_LABEL}: {revoked} session(s) revoked, {retired} passkey(s) retired.",
                tenant_id=None,
                after={"sessionsRevoked": revoked, "passkeysRetired": retired, "invitationId": str(issued.invitation.id)},
            )
            # The retired passkeys opened the person's banks too: end their sessions and personal
            # tokens there and tell each bank, last, as each one activates its bank (D-122).
            tokens_revoked = 0
            for bank_id, _ in banks:
                tenancy.activate(bank_id)
                in_bank = session_logic.revoke_all(user, tenant_id=bank_id, reason="reenrolment", actor=actor)
                tokens_here = api_keys_logic.revoke_person_tokens(tenant_id=bank_id, person=user, revoked_by=user, now=now)
                revoked += in_bank
                tokens_revoked += tokens_here
                record(
                    action="platform_staff.enrolment_reissued",
                    actor=actor,
                    subject_type="user",
                    subject_id=user.id,
                    subject_title=user.name,
                    summary=f"Enrolment re-issued by {ACTOR_LABEL}: {in_bank} session(s) here revoked, {retired} passkey(s) retired.",
                    tenant_id=bank_id,
                    after={"sessionsRevoked": in_bank, "passkeysRetired": retired, "tokensRevoked": tokens_here},
                )
        self.stdout.write(
            f"{user.name} ({user.id}) re-enrolment sent: {revoked} session(s) revoked, {retired} passkey(s) retired, "
            f"{tokens_revoked} personal token(s) revoked"
        )
        self.stdout.write(f"platform roles: {', '.join(a.role.key for a in assignments) or 'none'}")
        self.stdout.write(f"invitation link (valid once): {mail.invitation_link(issued.token)}")
