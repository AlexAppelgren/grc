"""Personal access tokens, and every key and token of a bank in one list (ACC-03, ACC-09, ADR 0056).

A member holding `tokens.create` mints a token for themselves from a session with a fresh
passkey assertion: it carries an expiry no later than `PERSONAL_TOKEN_MAX_DAYS`, holds only
reading scopes their own permissions back, may name one live entry of their bank, and is
shown once and stored as a hash. They list and revoke their own. An administrator holding
`integrations.manage` sees every key and token of the bank, with its kind and the entry or
person behind it, and revokes any of them. Every mint, use and revocation is a security-log
row of the token's own method, and every write an audit row."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from apps.identity.models import ApiKey, LoginEvent, LoginEventKind, LoginMethod, TenantRole
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"
READS = sorted(perms.AGENT_ACCESS_SCOPES)


class PersonalTokenCase(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = factories.tenant(slug="token-bank")
        self.officer = factories.member_user(self.bank, roles=("compliance_officer",))
        self.colleague = factories.member_user(self.bank, roles=("compliance_officer",))

    def _body(self, **changes: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper building a request body
        body: dict[str, Any] = {
            "name": "Laptop coding agent",
            "scopes": [perms.SCOPE_LIBRARY_READ, perms.SCOPE_SEARCH_READ],
            "expiresAt": (timezone.now() + timedelta(days=30)).isoformat(),
        }
        return body | changes

    def _mint(self, body: dict[str, Any], *, user: Any = None, step_up: bool = True) -> Any:
        headers = sign_in(user or self.officer, tenant=self.bank, step_up=step_up)
        return self.client.post(f"{V1}/me/tokens", data=body, content_type="application/json", **headers)

    def _events(self, key_id: Any, event: LoginEventKind) -> list[LoginEvent]:
        tenancy.activate(self.bank.id)
        return list(LoginEvent.objects.filter(api_key_id=key_id, event=event.value))


class MintingAToken(PersonalTokenCase):
    def test_a_member_mints_a_token_shown_once_hashed_and_expiring(self) -> None:
        response = self._mint(self._body())
        self.assertEqual(response.status_code, 201, response.content)
        created = response.json()
        plain = created["plainKey"]
        self.assertTrue(plain.startswith(f"cw_{created['keyPrefix']}_"))
        self.assertEqual(created["scopes"], [perms.SCOPE_LIBRARY_READ, perms.SCOPE_SEARCH_READ])
        self.assertIsNone(created["agentAccess"])
        self.activate(self.bank)
        row = ApiKey.objects.get(pk=created["id"])
        self.assertEqual((row.kind, row.acts_as_user_id, row.created_by_id, row.tenant_id), ("personal", self.officer.id, self.officer.id, self.bank.id))
        self.assertIsNotNone(row.expires_at)
        self.assertNotIn(plain.rsplit("_", 1)[1], row.key_hash, "only the hash is stored")
        (minted,) = self._events(row.id, LoginEventKind.TOKEN_CREATED)
        self.assertEqual((minted.method, minted.user_id, minted.success), (LoginMethod.PERSONAL_TOKEN.value, self.officer.id, True))
        (audit,) = AuditEvent.objects.filter(action="personal_token.created", subject_id=row.id)
        self.assertEqual((audit.actor_id, audit.tenant_id), (self.officer.id, self.bank.id))
        self.assertIsNotNone(audit.step_up_assertion_id)
        self.assertNotIn(plain, str(audit.after) + audit.summary, "the secret never reaches the audit row")
        # Listed afterwards without the secret.
        listed = self.client.get(f"{V1}/me/tokens", **sign_in(self.officer, tenant=self.bank)).json()
        self.assertEqual([item["id"] for item in listed["items"]], [created["id"]])
        self.assertNotIn("plainKey", listed["items"][0])

    def test_it_reads_as_the_member_and_never_beyond_its_scopes(self) -> None:
        plain = self._mint(self._body(scopes=[perms.SCOPE_LIBRARY_READ])).json()["plainKey"]
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=plain).status_code, 200)
        self.assertEqual(self.client.get(f"{V1}/upcoming", **sign_in(self.officer, tenant=self.bank)).status_code, 200)
        upcoming = self.client.get(f"{V1}/upcoming", HTTP_X_API_KEY=plain)
        self.assertEqual(upcoming.status_code, 403, "the member reads the dates coming up, the token was not given upcoming:read")

    def test_a_token_names_a_live_entry_of_the_bank(self) -> None:
        entry = factories.agent_access_entry(self.bank)
        response = self._mint(self._body(scopes=[perms.SCOPE_TENANT_READ], agentAccessId=str(entry.id)))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["agentAccess"], {"id": str(entry.id), "name": entry.row.name})
        other_bank_entry = factories.agent_access_entry(factories.tenant(slug="other-token-bank"))
        tenancy.activate(self.bank.id)
        type(entry.row).objects.filter(pk=entry.id).update(active=False, revoked_at=timezone.now(), revoked_by=entry.admin)
        for name, entry_id in (("revoked", entry.id), ("another bank's", other_bank_entry.id)):
            with self.subTest(name):
                refused = self._mint(self._body(agentAccessId=str(entry_id)))
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"), refused.content)

    def test_tenant_read_needs_an_entry(self) -> None:
        refused = self._mint(self._body(scopes=[perms.SCOPE_LIBRARY_READ, perms.SCOPE_TENANT_READ]))
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "entry_required"), refused.content)

    def test_the_gates(self) -> None:
        reader = factories.member_user(self.bank, roles=("reader",))
        cases = {
            "no step-up": (self._mint(self._body(), step_up=False), 403, "step_up_required"),
            "no tokens.create": (self._mint(self._body(), user=reader), 403, "permission_denied"),
        }
        for name, (response, status, code) in cases.items():
            with self.subTest(name):
                self.assertEqual((response.status_code, response.json()["code"]), (status, code), response.content)
        self.activate(self.bank)
        self.assertFalse(ApiKey.objects.filter(kind="personal").exists())

    def test_a_token_cannot_mint_a_token(self) -> None:
        token = factories.personal_token(self.bank, self.officer, scopes=READS)
        for header in ({"HTTP_X_API_KEY": token.plain_key}, {"HTTP_AUTHORIZATION": f"Bearer {token.plain_key}"}):
            response = self.client.post(f"{V1}/me/tokens", data=self._body(), content_type="application/json", **header)
            self.assertEqual((response.status_code, response.json()["code"]), (403, "step_up_required"), response.content)

    def test_the_expiry_is_required_future_and_bounded(self) -> None:
        now = timezone.now()
        cases = {
            "missing": ({k: v for k, v in self._body().items() if k != "expiresAt"}, "validation_error"),
            "null": (self._body(expiresAt=None), "validation_error"),
            "past": (self._body(expiresAt=(now - timedelta(minutes=1)).isoformat()), "expiry_in_past"),
            "too late": (self._body(expiresAt=(now + timedelta(days=settings.PERSONAL_TOKEN_MAX_DAYS, hours=1)).isoformat()), "expiry_too_late"),
        }
        for name, (body, code) in cases.items():
            with self.subTest(name):
                response = self._mint(body)
                self.assertEqual((response.status_code, response.json()["code"]), (422, code), response.content)
        longest = self._mint(self._body(expiresAt=(now + timedelta(days=settings.PERSONAL_TOKEN_MAX_DAYS, minutes=-1)).isoformat()))
        self.assertEqual(longest.status_code, 201, longest.content)

    @override_settings(PERSONAL_TOKEN_MAX_DAYS=7)
    def test_the_longest_life_is_a_setting(self) -> None:
        response = self._mint(self._body(expiresAt=(timezone.now() + timedelta(days=8)).isoformat()))
        self.assertEqual(response.json()["code"], "expiry_too_late")

    def test_scopes_are_reads_the_member_holds(self) -> None:
        self.activate(self.bank)
        narrow = TenantRole.objects.create(tenant=self.bank, key="token-library-only", permissions=[perms.LIBRARY_READ, perms.TOKENS_CREATE])
        narrow_member = factories.member(self.bank, roles=(narrow.key,)).user
        cases = {
            "a write": (self.officer, [perms.SCOPE_PROPOSALS_WRITE], "unknown_key"),
            "a platform scope": (self.officer, [perms.SCOPE_PROPOSALS_REVIEW], "unknown_key"),
            "a read the member cannot make": (narrow_member, [perms.SCOPE_LIBRARY_READ, perms.SCOPE_SEARCH_READ], "scope_not_held"),
        }
        for name, (user, scopes, code) in cases.items():
            with self.subTest(name):
                response = self._mint(self._body(scopes=scopes), user=user)
                self.assertEqual((response.status_code, response.json()["code"]), (422, code), response.content)
        allowed = self._mint(self._body(scopes=[perms.SCOPE_LIBRARY_READ]), user=narrow_member)
        self.assertEqual(allowed.status_code, 201, allowed.content)


class AMembersOwnTokens(PersonalTokenCase):
    def test_the_list_is_the_members_own_tokens_newest_first(self) -> None:
        older = factories.personal_token(self.bank, self.officer)
        newer = factories.personal_token(self.bank, self.officer)
        factories.personal_token(self.bank, self.colleague)
        factories.api_key(self.bank)
        page = self.client.get(f"{V1}/me/tokens?limit=1", **sign_in(self.officer, tenant=self.bank))
        self.assertEqual(page.status_code, 200, page.content)
        self.assertEqual((page.json()["total"], [item["id"] for item in page.json()["items"]]), (2, [str(newer.id)]))
        rest = self.client.get(f"{V1}/me/tokens?limit=1&offset=1", **sign_in(self.officer, tenant=self.bank)).json()
        self.assertEqual([item["id"] for item in rest["items"]], [str(older.id)])

    def test_a_member_revokes_their_own_token_and_it_stops(self) -> None:
        token = factories.personal_token(self.bank, self.officer)
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=token.plain_key).status_code, 200)
        for _attempt in range(2):
            response = self.client.delete(f"{V1}/me/tokens/{token.id}", **sign_in(self.officer, tenant=self.bank))
            self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=token.plain_key).status_code, 401)
        (revoked,) = self._events(token.id, LoginEventKind.TOKEN_REVOKED)
        self.assertEqual((revoked.method, revoked.user_id), (LoginMethod.PERSONAL_TOKEN.value, self.officer.id))
        audits = list(AuditEvent.objects.filter(action="personal_token.revoked", subject_id=token.id).order_by("created"))
        self.assertEqual(len(audits), 2, "the retry is audited too")
        self.assertEqual(audits[1].before, audits[1].after)

    def test_revoking_needs_no_tokens_create(self) -> None:
        """A member who lost the permission can still stop what they minted."""
        reader = factories.member_user(self.bank, roles=("reader",))
        token = factories.personal_token(self.bank, reader)
        response = self.client.delete(f"{V1}/me/tokens/{token.id}", **sign_in(reader, tenant=self.bank))
        self.assertEqual(response.status_code, 204, response.content)

    def test_only_the_members_own_token_is_found(self) -> None:
        theirs = factories.personal_token(self.bank, self.colleague)
        service = factories.api_key(self.bank)
        other_bank = factories.tenant(slug="token-other-bank")
        elsewhere = factories.personal_token(other_bank, factories.member_user(other_bank, roles=("compliance_officer",)))
        for name, key_id in (("a colleague's token", theirs.id), ("a service key", service.id), ("another bank's token", elsewhere.id)):
            with self.subTest(name):
                response = self.client.delete(f"{V1}/me/tokens/{key_id}", **sign_in(self.officer, tenant=self.bank))
                self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=theirs.plain_key).status_code, 200)


class EveryCredentialOfTheBank(PersonalTokenCase):
    def setUp(self) -> None:
        super().setUp()
        self.admin = factories.member_user(self.bank, roles=("admin",))
        self.entry = factories.agent_access_entry(self.bank)
        self.unbound = factories.api_key(self.bank, name="Policy portal sync")
        self.entry_key = factories.entry_key(self.bank, self.entry)
        self.token = factories.personal_token(self.bank, self.officer, entry=self.entry)

    def test_the_list_carries_each_kind_and_its_entry_or_person(self) -> None:
        page = self.client.get(f"{V1}/tenant/api-keys", **sign_in(self.admin, tenant=self.bank))
        self.assertEqual(page.status_code, 200, page.content)
        rows = {item["id"]: item for item in page.json()["items"]}
        self.assertEqual(page.json()["total"], 3)
        shape = {key: (rows[str(key)]["kind"], rows[str(key)]["agentAccess"], rows[str(key)]["person"]) for key in (self.unbound.id, self.entry_key.id, self.token.id)}
        entry_ref = {"id": str(self.entry.id), "name": self.entry.row.name}
        self.assertEqual(
            shape,
            {
                self.unbound.id: ("service", None, None),
                self.entry_key.id: ("service", entry_ref, None),
                self.token.id: ("personal", entry_ref, {"id": str(self.officer.id), "name": self.officer.name}),
            },
        )

    def test_an_admin_revokes_a_token_and_an_entry_key_each_with_its_own_log_row(self) -> None:
        for credential, event, method in (
            (self.token, LoginEventKind.TOKEN_REVOKED, LoginMethod.PERSONAL_TOKEN),
            (self.entry_key, LoginEventKind.KEY_REVOKED, LoginMethod.API_KEY),
        ):
            with self.subTest(method.value):
                response = self.client.delete(f"{V1}/tenant/api-keys/{credential.id}", **sign_in(self.admin, tenant=self.bank))
                self.assertEqual(response.status_code, 204, response.content)
                self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=credential.plain_key).status_code, 401)
                (revoked,) = self._events(credential.id, event)
                self.assertEqual((revoked.method, revoked.user_id), (method.value, self.admin.id))

    def test_the_list_and_revoke_stay_the_integrations_managers(self) -> None:
        headers = sign_in(self.officer, tenant=self.bank)
        self.assertEqual(self.client.get(f"{V1}/tenant/api-keys", **headers).status_code, 403)
        self.assertEqual(self.client.delete(f"{V1}/tenant/api-keys/{self.token.id}", **headers).status_code, 403)
