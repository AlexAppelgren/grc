"""What an agent access credential resolves to (ACC-03, ACC-04, ADR 0056), on real rows.

A key bound to an entry reads as the entry and stops the moment the entry is revoked; a
personal access token acts as its person and stops the moment the person, their
membership or the permission behind one of its scopes is gone; `tenant:read` reaches
nothing without an entry. Each is checked on the next request, never by a sweep. The audit
actor of each names the entry or the person."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.identity import api_keys_logic
from apps.identity.models import LoginEvent, LoginEventKind, LoginMethod, Membership, MembershipRole, TenantRole, User, UserStatus
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import ActorType, key_actor
from apps.shared.testing import ScenarioTestCase

V1 = "/api/v1"
READS = sorted(perms.AGENT_ACCESS_SCOPES)


class CredentialResolution(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = factories.tenant(slug="resolution-bank")
        self.entry = factories.agent_access_entry(self.bank)
        self.person = factories.member(self.bank, roles=("reader",)).user

    def _reads(self, credential: Any) -> int:
        return int(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=credential.plain_key).status_code)

    def test_an_entry_key_reads_as_its_entry_and_its_actor_is_the_entry(self) -> None:
        key = factories.entry_key(self.bank, self.entry, scopes=READS)
        principal = api_keys_logic.resolve_api_key(key.plain_key)
        assert principal is not None
        self.assertEqual((principal.agent_access_id, principal.agent_access_label), (self.entry.id, "Trading platform coding agent"))
        self.assertIsNone(principal.acting_user_id)
        self.assertTrue(principal.is_agent_access)
        self.assertEqual(principal.scopes, frozenset(READS), "an entry's key keeps tenant:read for its register read")
        actor = key_actor(principal)
        self.assertEqual((actor.kind, actor.id, actor.label), (ActorType.AGENT, self.entry.id, "Trading platform coding agent"))

    def test_revoking_the_entry_refuses_its_key_on_the_next_request(self) -> None:
        key = factories.entry_key(self.bank, self.entry)
        self.assertEqual(self._reads(key), 200)
        self.activate(self.bank)
        type(self.entry.row).objects.filter(pk=self.entry.id).update(active=False, revoked_at=timezone.now(), revoked_by=self.entry.admin)
        self.assertEqual(self._reads(key), 401)
        self.assertIsNone(api_keys_logic.resolve_api_key(key.plain_key))

    def test_a_token_acts_as_its_person_and_its_actor_is_the_person(self) -> None:
        token = factories.personal_token(self.bank, self.person, scopes=READS, entry=self.entry)
        principal = api_keys_logic.resolve_api_key(token.plain_key)
        assert principal is not None
        self.assertEqual((principal.acting_user_id, principal.acting_user_label), (self.person.id, self.person.name))
        self.assertEqual(principal.agent_access_id, self.entry.id)
        self.assertFalse(principal.has_permission(perms.LIBRARY_READ), "a token holds scopes, never a session's permissions")
        self.assertEqual(principal.scopes, frozenset(READS))
        actor = key_actor(principal)
        self.assertEqual((actor.kind, actor.id, actor.label), (ActorType.USER, self.person.id, self.person.name))
        self.activate(self.bank)
        used = LoginEvent.objects.filter(api_key_id=token.id, event=LoginEventKind.TOKEN_USED.value).first()  # ordering: one use inside the throttle
        assert used is not None
        self.assertEqual((used.method, used.user_id), (LoginMethod.PERSONAL_TOKEN.value, self.person.id))

    def test_a_token_dies_with_its_person_or_their_membership(self) -> None:
        cases = {
            "person deactivated": lambda person: User.objects.filter(pk=person.id).update(
                status=UserStatus.DEACTIVATED.value, deactivated_at=timezone.now()
            ),
            "membership deactivated": lambda person: Membership.objects.filter(tenant=self.bank, user=person).update(
                deactivated_at=timezone.now()
            ),
        }
        for name, end in cases.items():
            with self.subTest(name):
                person = factories.member(self.bank, roles=("reader",)).user
                token = factories.personal_token(self.bank, person)
                self.assertEqual(self._reads(token), 200)
                self.activate(self.bank)
                end(person)
                self.assertEqual(self._reads(token), 401)

    def test_a_token_dies_with_a_permission_one_of_its_scopes_stands_on(self) -> None:
        self.activate(self.bank)
        narrow = TenantRole.objects.create(tenant=self.bank, key="library-only", permissions=[perms.LIBRARY_READ])
        token = factories.personal_token(self.bank, self.person, scopes=[perms.SCOPE_LIBRARY_READ, perms.SCOPE_SEARCH_READ])
        self.assertEqual(self._reads(token), 200)
        self.activate(self.bank)
        membership = Membership.objects.get(tenant=self.bank, user=self.person)
        MembershipRole.objects.filter(membership=membership).delete()
        MembershipRole.objects.create(tenant=self.bank, membership=membership, role=narrow)
        self.assertEqual(self._reads(token), 401, "search:read no longer stands on search.use, so the token is refused")
        backed = factories.personal_token(self.bank, self.person, scopes=[perms.SCOPE_LIBRARY_READ])
        self.assertEqual(self._reads(backed), 200, "a token whose every scope is backed still reads")

    def test_each_scope_stands_on_the_permission_a_session_reads_it_with(self) -> None:
        self.assertEqual(
            api_keys_logic.SCOPE_BACKING,
            {
                perms.SCOPE_LIBRARY_READ: perms.LIBRARY_READ,
                perms.SCOPE_SEARCH_READ: perms.SEARCH_USE,
                perms.SCOPE_UPCOMING_READ: perms.ROADMAP_READ,
                perms.SCOPE_TENANT_READ: perms.REGISTER_READ,
            },
        )
        self.assertEqual(set(api_keys_logic.SCOPE_BACKING), set(perms.AGENT_ACCESS_SCOPES), "every scope a token may hold")

    def test_tenant_read_reaches_nothing_without_an_entry(self) -> None:
        unbound_key = factories.api_key(self.bank, scopes=[perms.SCOPE_LIBRARY_READ, perms.SCOPE_TENANT_READ])
        unbound_token = factories.personal_token(self.bank, self.person, scopes=[perms.SCOPE_LIBRARY_READ, perms.SCOPE_TENANT_READ])
        for name, credential in (("service key", unbound_key), ("personal token", unbound_token)):
            with self.subTest(name):
                principal = api_keys_logic.resolve_api_key(credential.plain_key)
                assert principal is not None
                self.assertEqual(principal.scopes, frozenset({perms.SCOPE_LIBRARY_READ}))
                self.activate(self.bank)
                withheld = LoginEvent.objects.filter(api_key_id=credential.id, event=LoginEventKind.KEY_SCOPES_WITHHELD.value).first()  # ordering: one row inside the throttle
                assert withheld is not None
                self.assertEqual(withheld.failure_reason, perms.SCOPE_TENANT_READ)
        bound = factories.personal_token(self.bank, self.person, scopes=[perms.SCOPE_TENANT_READ], entry=self.entry)
        principal = api_keys_logic.resolve_api_key(bound.plain_key)
        assert principal is not None
        self.assertEqual(principal.scopes, frozenset({perms.SCOPE_TENANT_READ}))

    def test_an_unbound_bank_key_and_a_platform_key_are_not_agent_access(self) -> None:
        from apps.agents import testing as agents_testing

        bank_key = factories.api_key(self.bank)
        tenancy.clear_tenant()
        platform_key = agents_testing.agent_key()
        for credential in (bank_key, platform_key):
            principal = api_keys_logic.resolve_api_key(credential.plain_key)
            assert principal is not None
            self.assertFalse(principal.is_agent_access)
            self.assertEqual((principal.agent_access_id, principal.acting_user_id), (None, None))
