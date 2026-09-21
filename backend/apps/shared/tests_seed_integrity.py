"""Guard: seed integrity (playbook 5, 8.3).

Runs the E2E seed and demands that two tenants exist with exactly the properties journeys
depend on (`EXPECTED_TENANTS`: fixed ids, slugs, names, timezones), that every fixed login
in `SEED_LOGINS` has exactly its roles, its passkey (the fixed credential id) or none, and
that the one user awaiting enrolment holds an open invitation whose token is the E2E
literal under E2E_MODE; that every login a journey spends (`reserved_for`, playbook 8.3
rule 4) is reserved for one journey, starts active with its fixed passkey and never holds
a role another journey needs it for; that two library editors hold the console, so a
proposal can be decided by someone other than its author; that the seed is idempotent (a second run changes nothing and adds
no audit row), writes its audit rows through record(), and refuses to run on a deployed
environment. A journey cannot be hollowed out by a seed change without failing here.

Proven to fail 2026-09-19 by changing TENANT_B's slug in the seed but not in EXPECTED:
the test named the tenant and the property.
"""

from __future__ import annotations

import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.cases.models import ChangeCase
from apps.home.models import Briefing, BriefingItem
from apps.home.roadmap import quarter_of
from apps.identity import tokens
from apps.identity.models import Invitation, Membership, PlatformRoleAssignment, User, UserStatus, WebAuthnCredential
from apps.shared import tenancy
from apps.shared.e2e_logins import (
    E2E_INVITATION_TOKEN_ANNA,
    LIBRARY_EDITOR_ROLE,
    REISSUE_LOGIN_EMAIL,
    SEED_LOGINS,
    TENANT_A_SLUG,
    TENANT_B_SLUG,
)
from apps.shared.e2e_passkeys import E2E_PASSKEYS
from apps.library.models import Instrument, Obligation, ObligationVersion, Verification
from apps.shared.e2e_seed import (
    EXPECTED_FOOTPRINTS,
    EXPECTED_HOME,
    EXPECTED_LIBRARY,
    EXPECTED_PENDING_REQUEST,
    EXPECTED_TENANTS,
    SeedRefused,
    _quarter_safe_offsets,
    seed_e2e,
)
from apps.shared.models import AuditEvent, Tenant
from apps.watch.models import CheckStatus, RegulatoryChange, SourceCheck
from apps.taxonomy.matching import footprint_of, in_footprint, restricting_dimensions
from apps.taxonomy.models import FootprintChangeRequest, FootprintHistory, FootprintTerm
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.tenant_hooks import TENANT_SYSTEM_ROWS


def _scope(obligation: Obligation) -> dict[str, set[str]]:
    """An obligation's scope: its own terms plus its instrument's regime."""
    scope: dict[str, set[str]] = {}
    for term in obligation.terms.all():
        scope.setdefault(term.dimension.key, set()).add(term.key)
    regime = obligation.instrument.regime
    if regime is not None:
        scope.setdefault(regime.dimension.key, set()).add(regime.key)
    return scope


@override_settings(E2E_MODE=True)
class SeedIntegrityGuard(TestCase):
    def test_the_seed_creates_exactly_the_expected_tenants(self) -> None:
        counts = seed_e2e()
        self.assertEqual(counts["tenants"], 2)
        self.assertEqual(len(EXPECTED_TENANTS), 2, "journeys need two tenants (J-8)")
        for expected in EXPECTED_TENANTS:
            with self.subTest(tenant=expected.slug):
                row = Tenant.objects.get(slug=expected.slug)
                self.assertEqual(row.id, expected.id)
                self.assertEqual(row.name, expected.name)
                self.assertEqual(row.timezone, expected.timezone)
                assert row.default_language is not None
                self.assertEqual(row.default_language.key, expected.content_languages[0])
        self.assertEqual(Tenant.objects.count(), 2)
        slugs = {t.slug for t in EXPECTED_TENANTS}
        self.assertEqual(len(slugs), 2, "seed tenants must have distinct slugs")

    def test_every_fixed_login_has_exactly_its_roles_and_passkey(self) -> None:
        counts = seed_e2e()
        self.assertEqual(counts["logins"], len(SEED_LOGINS))
        tenants = {t.slug: t for t in Tenant.objects.all()}
        awaiting = [login for login in SEED_LOGINS if login.awaiting_enrolment]
        self.assertEqual(len(awaiting), 1, "exactly one seeded user awaits enrolment (J-1)")
        for login in SEED_LOGINS:
            with self.subTest(login=login.email):
                user = User.objects.get(email=login.email)
                self.assertEqual(user.id, login.id)
                self.assertEqual(user.name, login.name)
                expected_status = UserStatus.INVITED if login.awaiting_enrolment else UserStatus.ACTIVE
                self.assertEqual(user.status, expected_status.value)
                assert user.locale is not None, "every seeded login has a locale (journeys run in one pinned language)"
                self.assertEqual(user.locale.key, login.locale)
                if login.tenant_slug:
                    tenancy.activate(tenants[login.tenant_slug].id)
                    if login.awaiting_enrolment:
                        self.assertFalse(Membership.objects.filter(user=user).exists())
                        invitation = Invitation.objects.get(email=login.email, accepted_at__isnull=True, revoked_at__isnull=True)
                        self.assertEqual(invitation.token_hash, tokens.hash_token(E2E_INVITATION_TOKEN_ANNA))
                        self.assertEqual(sorted(invitation.role_links.values_list("role__key", flat=True)), sorted(login.tenant_roles))
                    else:
                        membership = Membership.objects.get(user=user, tenant=tenants[login.tenant_slug])
                        self.assertEqual(sorted(membership.roles.values_list("key", flat=True)), sorted(login.tenant_roles))
                else:
                    self.assertFalse(Membership.objects.filter(user=user).exists())
                platform = sorted(PlatformRoleAssignment.objects.filter(user=user).values_list("role__key", flat=True))
                self.assertEqual(platform, sorted(login.platform_roles))
                live = WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True)
                if login.has_passkey:
                    self.assertEqual(live.count(), 1)
                    self.assertEqual(live.get().credential_id, E2E_PASSKEYS[login.email].credential_id)
                    self.assertEqual(live.get().public_key, E2E_PASSKEYS[login.email].public_key_cose)
                else:
                    self.assertEqual(live.count(), 0)

    def test_logins_spent_by_a_journey_are_dedicated_to_it(self) -> None:
        """ADM-S2 re-issues an enrolment, which retires the member's passkeys and sets them
        back to invited, and the UI cannot undo it. It spends a login of its own, so the
        approver the footprint journeys sign in as survives a full run."""
        seed_e2e()
        reserved = [login for login in SEED_LOGINS if login.reserved_for]
        by_email = {login.email: login for login in SEED_LOGINS}
        self.assertIn(REISSUE_LOGIN_EMAIL, by_email, "ADM-S2 needs its dedicated login in the roster")
        self.assertEqual(by_email[REISSUE_LOGIN_EMAIL].reserved_for, ("ADM-S2",))
        scenarios = [scenario for login in reserved for scenario in login.reserved_for]
        self.assertEqual(len(scenarios), len(set(scenarios)), "a journey spends one dedicated login, and no two journeys share one")
        # The system-role logins other journeys sign in as are never the ones spent.
        shared_roles = {"admin", "compliance_officer", "owner", "approver", "reader", "auditor"}
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        for login in reserved:
            with self.subTest(login=login.email):
                self.assertTrue(login.has_passkey, "it must hold a passkey for re-issue to retire")
                self.assertFalse(login.awaiting_enrolment)
                self.assertFalse(set(login.tenant_roles) & shared_roles, "a spent login never holds a role a shared login stands for")
                user = User.objects.get(email=login.email)
                self.assertEqual(user.status, UserStatus.ACTIVE.value)
                self.assertEqual(WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).get().credential_id, E2E_PASSKEYS[login.email].credential_id)
                membership = Membership.objects.get(user=user, tenant=tenant_a)
                # ADM-S2 grants Reader and then proves the row shows it, so the seed must not.
                self.assertNotIn("reader", set(membership.roles.values_list("key", flat=True)))
        # The approver stays shared: the footprint journeys (FP-S2, FP-S5) sign in as them.
        self.assertEqual(by_email["approver@example-bank.test"].reserved_for, ())

    def test_two_library_editors_hold_the_console_so_four_eyes_can_hold(self) -> None:
        """PRO-02, AC-PRO2: a proposal is decided by someone other than its author, and in
        the console the author is a library editor too. One seeded editor would make the
        queue journeys unrunnable, so the roster carries two, both platform staff (no
        tenant) with their fixed passkeys."""
        seed_e2e()
        editors = [login for login in SEED_LOGINS if LIBRARY_EDITOR_ROLE in login.platform_roles]
        self.assertGreaterEqual(len(editors), 2, "a proposal needs a second editor to decide it")
        for login in editors:
            with self.subTest(login=login.email):
                self.assertIsNone(login.tenant_slug, "a library editor is platform staff, never a bank's member")
                self.assertTrue(login.has_passkey)
                user = User.objects.get(email=login.email)
                granted = PlatformRoleAssignment.objects.filter(user=user, role__key=LIBRARY_EDITOR_ROLE)
                self.assertEqual(granted.count(), 1)

    def test_the_seed_is_idempotent_and_audited(self) -> None:
        seed_e2e()
        audited = AuditEvent.objects.filter(action="tenant.seeded").count()
        self.assertEqual(audited, 2, "each seeded tenant leaves one audit row through record()")
        users, memberships, credentials = User.objects.count(), Membership.objects.count(), WebAuthnCredential.objects.count()
        seed_e2e()
        self.assertEqual(Tenant.objects.count(), 2)
        self.assertEqual(AuditEvent.objects.filter(action="tenant.seeded").count(), 2)
        self.assertEqual((User.objects.count(), Membership.objects.count(), WebAuthnCredential.objects.count()), (users, memberships, credentials))
        with tenancy.identity_lookup():
            self.assertEqual(Invitation.objects.filter(accepted_at__isnull=True, revoked_at__isnull=True).count(), 1)
        # Each tenant's own list rows are recorded as this seed's work, not as a deploy's.
        for tenant in Tenant.objects.all():
            tenancy.activate(tenant.id)
            created = AuditEvent.objects.filter(tenant=tenant, action="vocabulary.created")
            self.assertEqual(created.count(), sum(len(rows) for _, rows in TENANT_SYSTEM_ROWS.values()))
            self.assertEqual(set(created.values_list("actor_label", flat=True)), {"seed_e2e"})

    def test_each_tenant_has_exactly_its_seeded_footprint_and_the_pending_request(self) -> None:
        """Chunk 2 (J-5, J-6): tenant A carries the prototype's footprint, tenant B a
        different one, every tenant its system vocabulary rows, and one pending footprint
        request authored by the compliance officer waits for the approver."""
        seed_e2e()
        for expected in EXPECTED_TENANTS:
            with self.subTest(tenant=expected.slug):
                tenant = Tenant.objects.get(slug=expected.slug)
                tenancy.activate(tenant.id)
                terms = {f"{row.term.dimension.key}:{row.term.key}" for row in FootprintTerm.objects.filter(tenant=tenant).select_related("term__dimension")}
                self.assertEqual(terms, set(EXPECTED_FOOTPRINTS[expected.slug]))
                self.assertEqual(FootprintHistory.objects.filter(tenant=tenant, action="added").count(), len(terms))
                for name, entry in REGISTRY.items():
                    if entry.tier == 3:
                        self.assertTrue(entry.model._default_manager.filter(tenant=tenant, is_system=True, active=True).exists(), name)
        self.assertNotEqual(set(EXPECTED_FOOTPRINTS[TENANT_A_SLUG]), set(EXPECTED_FOOTPRINTS[TENANT_B_SLUG]), "J-8 needs two different footprints")
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        pending = FootprintChangeRequest.objects.filter(tenant=tenant_a, status="pending")
        self.assertEqual(pending.count(), 1)
        request = pending.get()
        self.assertEqual(request.requested_by.email, EXPECTED_PENDING_REQUEST.requested_by_email)
        self.assertEqual({f"{t.dimension.key}:{t.key}" for t in request.removes.all()}, set(EXPECTED_PENDING_REQUEST.removes))
        self.assertEqual({f"{t.dimension.key}:{t.key}" for t in request.adds.all()}, set(EXPECTED_PENDING_REQUEST.adds))
        # The seeded request removes Advice, which hides the one advice-only obligation.
        self.assertEqual(request.preview["obligations"], {"hidden": 1, "revealed": 0, "available": True})
        # Idempotent: a second run keeps one request and the same footprint rows.
        seed_e2e()
        tenancy.activate(tenant_a.id)
        self.assertEqual(FootprintChangeRequest.objects.filter(tenant=tenant_a).count(), 1)
        self.assertEqual(FootprintTerm.objects.filter(tenant=tenant_a).count(), len(EXPECTED_FOOTPRINTS[TENANT_A_SLUG]))
        self.assertEqual(FootprintHistory.objects.filter(tenant=tenant_a).count(), len(EXPECTED_FOOTPRINTS[TENANT_A_SLUG]))

    def test_the_library_holds_the_prototype_instruments_and_obligations(self) -> None:
        """Chunk 3 (INV-01..INV-05, J-6): the prototype's instruments and obligations, the
        research payment obligation with a second version still in the future on the
        fixture's anchor date, and an English and a Swedish summary on every version."""
        counts = seed_e2e()
        self.assertEqual((counts["instruments"], counts["obligations"]), (EXPECTED_LIBRARY.instruments, EXPECTED_LIBRARY.obligations))
        self.assertEqual(Instrument.objects.count(), EXPECTED_LIBRARY.instruments)
        self.assertEqual(Obligation.objects.count(), EXPECTED_LIBRARY.obligations)
        research = list(ObligationVersion.objects.filter(obligation__stable_key=EXPECTED_LIBRARY.research_obligation))
        self.assertEqual([v.version_number for v in research], [1, 2])
        assert research[1].effective_from is not None
        self.assertGreater(research[1].effective_from, EXPECTED_LIBRARY.anchor_date, "version 2 must still be in the future")
        for version in ObligationVersion.objects.prefetch_related("summaries"):
            with self.subTest(version=str(version)):
                self.assertTrue({"en", "sv"} <= {row.language_id for row in version.summaries.all()})
        seed_e2e()
        self.assertEqual((Instrument.objects.count(), Obligation.objects.count()), (EXPECTED_LIBRARY.instruments, EXPECTED_LIBRARY.obligations))
        self.assertEqual(ObligationVersion.objects.filter(obligation__stable_key=EXPECTED_LIBRARY.research_obligation).count(), 2)

    def test_switching_off_advice_hides_an_obligation_of_tenant_a(self) -> None:
        """J-6, FP-01, FP-03, AC-FP1: the pending request switches Advice off. With Advice in
        tenant A's footprint no obligation is hidden; without it at least one is, the
        advice-only sample obligation among them."""
        seed_e2e()
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        footprint = footprint_of(tenant_a.id)
        without = {dimension: set(keys) for dimension, keys in footprint.items()}
        for ref in EXPECTED_PENDING_REQUEST.removes:
            dimension, key = ref.split(":")
            without[dimension].discard(key)
        restricting = restricting_dimensions()
        scopes = {
            o.stable_key: _scope(o) for o in Obligation.objects.select_related("instrument__regime__dimension").prefetch_related("terms__dimension")
        }
        self.assertEqual([key for key, scope in scopes.items() if not in_footprint(scope, footprint, restricting=restricting)], [])
        hidden = [key for key, scope in scopes.items() if not in_footprint(scope, without, restricting=restricting)]
        self.assertIn(EXPECTED_LIBRARY.advice_only_obligation, hidden)

    def test_every_instrument_and_obligation_has_a_source_link_and_a_verified_date(self) -> None:
        """INV-06, INV-S7: the card shows the source link and "Verified <date>" on every record."""
        seed_e2e()
        rows = [(row.stable_key, row.source_url, row.last_verified_at) for row in Instrument.objects.all()]
        rows += [(row.stable_key, row.source_url, row.last_verified_at) for row in Obligation.objects.all()]
        for key, source_url, verified_at in rows:
            with self.subTest(record=key):
                self.assertTrue(source_url)
                self.assertIsNotNone(verified_at)

    def test_no_library_verifier_is_a_tenant_member(self) -> None:
        """Regression pin (INV-06, INV-S8): a library record is verified by a library editor,
        never by a bank's user. The fixture names a tenant user (sara) as verifier, so the
        seed names nobody until a re-verification does. Proven to fail 2026-09-19 by
        stamping the compliance officer as an obligation's verifier after the seed."""
        seed_e2e()
        verifiers = {
            *Instrument.objects.exclude(verified_by=None).values_list("verified_by", flat=True),
            *Obligation.objects.exclude(verified_by=None).values_list("verified_by", flat=True),
            *Verification.objects.exclude(verified_by=None).values_list("verified_by", flat=True),
        }
        members: set[object] = set()
        for tenant in Tenant.objects.all():
            tenancy.activate(tenant.id)
            members |= set(Membership.objects.filter(tenant=tenant).values_list("user_id", flat=True))
        self.assertTrue(members, "the pin needs the seeded members to compare against")
        self.assertEqual(verifiers & members, set())

    def test_the_command_prints_counts(self) -> None:
        out = StringIO()
        call_command("seed_e2e", stdout=out)
        self.assertIn("tenants: 2", out.getvalue())
        self.assertIn(f"logins: {len(SEED_LOGINS)}", out.getvalue())

    @override_settings(IS_DEPLOYED_ENVIRONMENT=True, ENVIRONMENT="prod")
    def test_the_seed_refuses_a_deployed_environment(self) -> None:
        with self.assertRaises(SeedRefused):
            seed_e2e()
        self.assertEqual(Tenant.objects.count(), 0)

    def test_chunk_6_seeds_the_lead_case_the_out_of_scope_case_and_the_failed_source_check(self) -> None:
        """c6-e2e-seed (HOM-01, HOM-03): named here so a later change to the seed cannot
        quietly hollow HOM-S1, HOM-S2, HOM-S4 and HOM-S6 out without failing this guard."""
        seed_e2e()
        tenant = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant.id)

        lead = ChangeCase.objects.select_related("change").get(change__stable_key=EXPECTED_HOME.lead_change)
        self.assertTrue(lead.footprint_match)
        self.assertTrue(lead.so_what_confirmed, "the lead card and the briefing need a person's own words, not an AI draft")

        outside = ChangeCase.objects.get(change__stable_key=EXPECTED_HOME.outside_scope_change)
        self.assertFalse(outside.footprint_match, "the roadmap and Today's 'Coming up' must have something that must not appear")

        failed = SourceCheck.objects.select_related("source").get(source__name=EXPECTED_HOME.failed_source)
        self.assertEqual(failed.status, CheckStatus.FAILED.value)
        healthy = SourceCheck.objects.select_related("source").get(source__name=EXPECTED_HOME.healthy_source)
        self.assertEqual(healthy.status, CheckStatus.OK.value)

        # The weekly briefing for last week is already sent and snapshotted (ruling 17),
        # so `c6-briefing-screen`'s journey can open a past week without waiting for the beat.
        self.assertEqual(Briefing.objects.count(), 1)
        briefing = Briefing.objects.get()
        self.assertIsNotNone(briefing.email_sent_at)
        self.assertEqual(
            [item.case.change.stable_key for item in BriefingItem.objects.filter(briefing=briefing).select_related("case__change")],
            [EXPECTED_HOME.last_week_change],
        )

        # Tenant B's own two dates (J-8): present under its own tenant, and never reachable
        # once tenant A is the one activated.
        second_bank = Tenant.objects.get(slug=TENANT_B_SLUG)
        tenancy.activate(second_bank.id)
        self.assertEqual(ChangeCase.objects.count(), 2)
        tenancy.activate(tenant.id)
        self.assertEqual(ChangeCase.objects.filter(change__stable_key__startswith="chg-e2e-tenant-b").count(), 0)

    def test_chunk_6_seed_is_idempotent(self) -> None:
        seed_e2e()
        cases, checks, changes, briefings = (
            ChangeCase.objects.count(),
            SourceCheck.objects.count(),
            RegulatoryChange.objects.filter(stable_key__startswith="chg-e2e-").count(),
            Briefing.objects.count(),
        )
        self.assertGreater(cases, 0)

        seed_e2e()

        self.assertEqual(ChangeCase.objects.count(), cases)
        self.assertEqual(SourceCheck.objects.count(), checks)
        self.assertEqual(RegulatoryChange.objects.filter(stable_key__startswith="chg-e2e-").count(), changes)
        self.assertEqual(Briefing.objects.count(), briefings, "re-running the job for a sent week sends nothing and writes nothing")

    def test_the_seeded_dates_land_in_two_quarters_whatever_day_this_runs_on(self) -> None:
        """The near and far offsets `_quarter_safe_offsets()` derives stay in two different
        quarters on four anchors a quarter apart (CLAUDE.md §11): the seed never depends on
        which real day it happens to run on."""
        near, far = _quarter_safe_offsets()
        for anchor in (
            datetime.date(2026, 1, 1),
            datetime.date(2026, 4, 15),
            datetime.date(2026, 7, 31),
            datetime.date(2026, 10, 1),
        ):
            with self.subTest(anchor=anchor):
                self.assertNotEqual(quarter_of(anchor + datetime.timedelta(days=near)), quarter_of(anchor + datetime.timedelta(days=far)))
