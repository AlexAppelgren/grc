"""Findings of the security review of agent access and the bank's own records
(security-review-c11-access-d89, docs/reviews/CHUNK11_ACCESS_OWN_REVIEW.md) on personal
access tokens. Each test was written first and failed before its fix.

H1: a token dies with its person (AGENT_ACCESS.md section 8), but it was only refused while
the person was removed or deactivated, never revoked. A member re-invited after removal, or
enrolled again after ID-05's re-enrolment (a lost or stolen laptop), found every token they
had minted working again, with no revocation in the security log.
"""

from __future__ import annotations

from django.test import TestCase

from apps.identity import invitation_logic, members_logic
from apps.identity.models import ApiKey, LoginEvent, LoginEventKind, Membership, User, UserStatus
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent

READ = "/api/v1/obligations"


class ATokenDiesWithItsPerson(TestCase):
    def setUp(self) -> None:
        seed_languages()
        self.bank = factories.tenant(slug="token-death")
        self.admin = factories.member(self.bank, roles=("admin",)).user
        self.person = factories.member(self.bank, roles=("compliance_officer",)).user
        self.token = factories.personal_token(self.bank, self.person)
        self.actor = Actor(kind=ActorType.USER, id=self.admin.id, label=self.admin.name)
        self.assertEqual(self.read().status_code, 200)

    def read(self):  # type: ignore[no-untyped-def]
        return self.client.get(READ, HTTP_X_API_KEY=self.token.plain_key)

    def assert_revoked(self, action: str) -> None:
        tenancy.activate(self.bank.id)
        self.assertIsNotNone(ApiKey.objects.get(pk=self.token.id).revoked_at)
        self.assertTrue(LoginEvent.objects.filter(api_key_id=self.token.id, event=LoginEventKind.TOKEN_REVOKED.value).exists())
        self.assertEqual(AuditEvent.objects.filter(action=action).latest("created").after["tokensRevoked"], 1)

    def test_re_enrolment_revokes_the_persons_tokens(self) -> None:
        tenancy.activate(self.bank.id)
        invitation_logic.reissue_enrolment(
            tenant=self.bank, user=self.person, actor=self.actor, actor_user=self.admin, request=None, step_up_assertion_id=None
        )
        self.assertEqual(self.read().status_code, 401)
        self.assert_revoked("member.enrolment_reissued")
        # Enrolled again with a new passkey: the old token stays dead.
        User.objects.filter(pk=self.person.id).update(status=UserStatus.ACTIVE.value)
        self.assertEqual(self.read().status_code, 401)

    def test_removal_revokes_the_persons_tokens_so_a_new_invitation_brings_none_back(self) -> None:
        tenancy.activate(self.bank.id)
        members_logic.deactivate_member(tenant=self.bank, actor=self.actor, user_id=self.person.id, request=None)
        self.assertEqual(self.read().status_code, 401)
        self.assert_revoked("member.deactivated")
        # Invited again: the membership is active once more, and the old token stays dead.
        tenancy.activate(self.bank.id)
        Membership.objects.filter(tenant=self.bank, user=self.person).update(deactivated_at=None)
        self.assertEqual(self.read().status_code, 401)
