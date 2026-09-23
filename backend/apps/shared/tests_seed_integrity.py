"""Guard: seed integrity (playbook 5, 8.3).

Runs the E2E seed and demands that two tenants exist with exactly the properties journeys
depend on (`EXPECTED_TENANTS`: fixed ids, slugs, names, timezones), that every fixed login
in `SEED_LOGINS` has exactly its roles, its passkey (the fixed credential id) or none, and
that the one user awaiting enrolment holds an open invitation whose token is the E2E
literal under E2E_MODE; that every login a journey spends (`reserved_for`, playbook 8.3
rule 4) is reserved for one journey, starts active with its fixed passkey and never holds
a role another journey needs it for; that two library editors hold the console, so a
proposal can be decided by someone other than its author; that one proposal waits in the
console queue for every journey that decides one, each on a target of its own and each with
a source for every field it changes, and that one open problem report waits inside tenant A
for the journey that answers it; that the seed is idempotent (a second run changes nothing and adds
no audit row), writes its audit rows through record(), and refuses to run on a deployed
environment. A journey cannot be hollowed out by a seed change without failing here.

Proven to fail 2026-09-19 by changing TENANT_B's slug in the seed but not in EXPECTED:
the test named the tenant and the property.
"""

from __future__ import annotations

import datetime
from collections import Counter
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.agents.models import AgentRun
from apps.cases.models import ChangeCase
from apps.governance.models import AiGeneration
from apps.home.models import Briefing, BriefingItem
from apps.home.roadmap import quarter_of
from apps.identity import tokens
from apps.identity.models import ApiKey, Invitation, Membership, PlatformRoleAssignment, User, UserStatus, WebAuthnCredential
from apps.shared import tenancy
from apps.shared.adapters.mailer import MockMailer, OutgoingMail
from apps.shared.e2e_logins import (
    E2E_INVITATION_TOKEN_ANNA,
    LIBRARY_EDITOR_ROLE,
    REISSUE_LOGIN_EMAIL,
    SEED_LOGINS,
    TENANT_A_SLUG,
    TENANT_B_SLUG,
)
from apps.shared.e2e_passkeys import E2E_PASSKEYS
from apps.library.models import Authority, DatePrecision, Instrument, Obligation, ObligationVersion, ProblemReport, ReportStatus, Verification
from apps.proposals.logic import parsed_payload, sourced_fields
from apps.proposals.models import Proposal, ProposalStatus, ProposalTenant
from apps.search.models import SearchChunk, SearchSource
from apps.shared.e2e_seed import (
    CONFIRMED_LINK_OBLIGATION,
    E2E_STANDARD_INSTRUMENT,
    E2E_STANDARD_OBLIGATION,
    EXPECTED_CHUNK5_WATCH,
    EXPECTED_FOOTPRINTS,
    EXPECTED_HOME,
    EXPECTED_LIBRARY,
    EXPECTED_MACHINE_CONFIRMED,
    EXPECTED_OUTSIDE_SCOPE,
    EXPECTED_PENDING_REQUEST,
    EXPECTED_PROBLEM_REPORT,
    EXPECTED_PROPOSALS,
    EXPECTED_STANDARD_CHANGE,
    EXPECTED_TENANT_A_ONLY,
    EXPECTED_TENANTS,
    EXPECTED_WATCHED_MARKETS,
    WATCHED_MARKET_OBLIGATION,
    PRO_S7_OBLIGATION,
    PRO_S13_OBLIGATION,
    PRO_S13_RUN,
    RECHECK_OBLIGATION,
    SUGGESTED_LINK_OBLIGATION,
    SeedProposal,
    SeedRefused,
    _quarter_safe_offsets,
    seed_e2e,
)
from apps.shared.models import AuditEvent, Tenant
from apps.watch.models import ChangeDocument, ChangeEvent, ChangeObligation, ChangeTerm, CheckStatus, RegulatoryChange, Source, SourceCheck, SourceCheckKind
from apps.taxonomy.matching import footprint_of, in_footprint, in_footprint_sql, opt_in_dimensions, restricting_dimensions
from apps.taxonomy.models import FootprintChangeRequest, FootprintHistory, FootprintTerm, TaxonomyTerm, WatchedMarket
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


def _waiting_for(expected: SeedProposal) -> list[Proposal]:
    """The open proposals of this journey's kind on this journey's target: an obligation by
    its stable key, a vocabulary row by the list and key its payload names."""
    open_of_kind = Proposal.objects.filter(
        kind=expected.kind,
        status=ProposalStatus.OPEN.value,
    )
    if ":" in expected.target:
        list_name, key = expected.target.split(":")
        return list(open_of_kind.filter(
            payload__list=list_name,
            payload__key=key,
        ))
    return list(open_of_kind.filter(
        target_id=Obligation.objects.get(stable_key=expected.target).id,
    ))


# The sweeper key's runs per status: chunk 5's closed run and its open run, plus the open
# run each of the four agent proposals the seed files through that key is attached to.
EXPECTED_SWEEPER_RUNS = Counter({"succeeded": 1, "running": 5})


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
            # TEN-S7's one tenant-A tag is the seed's work too, but not a system row.
            system = created.exclude(subject_title=f"{EXPECTED_TENANT_A_ONLY.tag_list}:{EXPECTED_TENANT_A_ONLY.tag_key}")
            self.assertEqual(system.count(), sum(len(rows) for _, rows in TENANT_SYSTEM_ROWS.values()))
            self.assertEqual(set(created.values_list("actor_label", flat=True)), {"seed_e2e"})

    def test_each_tenant_has_exactly_its_seeded_footprint_and_the_pending_request(self) -> None:
        """Chunk 2 (J-5, J-6): tenant A carries the prototype's footprint less FP-S4's one
        outside term, tenant B a different one, every tenant its system vocabulary rows, and
        one pending footprint request authored by the compliance officer waits for the
        approver."""
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

    def test_the_search_index_is_built_and_fully_embedded_from_the_seeded_library(self) -> None:
        """SRC-01, J-7 (c7-e2e-seed): `seed_search_index()` runs `reindex_all()` and
        `embed_backlog()` inside the seed's own transaction, so a journey that searches the
        moment the seed finishes never races the outbox worker for a vector that has not
        arrived: SRC-S1's concept leg ("nudging in onboarding") only ever hits because every
        seeded chunk already carries its mock vector. FFFS 2017:2's provision tree (T8) now
        carries its own text versions, so both the obligation and the provision source types
        are indexed; every chunk is shared library data (D-10, H7): `owner_tenant_id` is
        NULL, never a bank's."""
        counts = seed_e2e()
        self.assertGreater(counts["search_chunks"], 0)
        self.assertEqual(SearchChunk.objects.count(), counts["search_chunks"])
        self.assertGreater(SearchChunk.objects.filter(source_type=SearchSource.OBLIGATION_VERSION.value).count(), 0)
        self.assertGreater(SearchChunk.objects.filter(source_type=SearchSource.PROVISION_VERSION.value).count(), 0)
        self.assertFalse(
            SearchChunk.objects.filter(embedding__isnull=True).exists(),
            "a journey must never race an embedding that has not arrived yet",
        )
        self.assertFalse(
            SearchChunk.objects.exclude(owner_tenant__isnull=True).exists(),
            "only the shared library is indexed in R1 (D-10)",
        )
        # Idempotent: a second run leaves the same chunks, not a duplicate set.
        seed_e2e()
        self.assertEqual(SearchChunk.objects.count(), counts["search_chunks"])

    def test_switching_off_advice_hides_an_obligation_of_tenant_a(self) -> None:
        """J-6, FP-01, FP-03, AC-FP1: the pending request switches Advice off. With Advice in
        tenant A's footprint the only obligation its own terms and regime hide is FP-S4's
        outside one (`EXPECTED_OUTSIDE_SCOPE`); without it at least one more is, the
        advice-only sample obligation among them. `_scope()` derives no jurisdiction, so the
        Danish and Norwegian rules tenant A's Swedish scope hides are FP-S13's, not these."""
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
        # The E2E standard's duty is hidden too: tenant A follows no standard.
        self.assertEqual(
            sorted(key for key, scope in scopes.items() if not in_footprint(scope, footprint, restricting=restricting)),
            sorted([EXPECTED_OUTSIDE_SCOPE.obligation, E2E_STANDARD_OBLIGATION]),
        )
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

    def test_each_journey_that_decides_a_proposal_finds_one_waiting_for_it(self) -> None:
        """chunk4-T8 (PRO-01, PRO-02, PRO-03): one open proposal per journey that spends one,
        each on a target of its own, each carrying a source for every field it changes, and
        none of them made inside a bank — a seeded proposal is the platform's, so the console
        can show it whole."""
        counts = seed_e2e()
        self.assertEqual(counts["proposals"], len(EXPECTED_PROPOSALS))
        journeys = [expected.journey for expected in EXPECTED_PROPOSALS]
        self.assertEqual(len(journeys), len(set(journeys)), "no two journeys share one seeded proposal")
        targets = [expected.target for expected in EXPECTED_PROPOSALS]
        self.assertEqual(len(targets), len(set(targets)), "no two seeded proposals sit on one target")
        for expected in EXPECTED_PROPOSALS:
            with self.subTest(journey=expected.journey):
                waiting = _waiting_for(expected)
                self.assertEqual(len(waiting), 1, "exactly one proposal of that kind waits on that target")
                proposal = waiting[0]
                self.assertFalse(proposal.proposed_in_tenant)
                self.assertEqual(ProposalTenant.objects.filter(proposal=proposal).count(), 0)
                self.assertIsNone(proposal.reviewed_at)
                # A source per changed field and none besides (PRO-01): the obligation kinds
                # carry one per summary language, one for the date and one for the scope they
                # change; a vocabulary label is a person's wording and carries none.
                self.assertEqual(sorted(proposal.field_sources), sorted(sourced_fields(parsed_payload(proposal.kind, proposal.payload))))
                if expected.proposed_by_email:
                    assert proposal.proposed_by_user is not None
                    self.assertEqual(proposal.proposed_by_user.email, expected.proposed_by_email)
                else:
                    self.assertIsNone(proposal.proposed_by_user, "an agent's proposal names no person, so any editor may decide it")
                    self.assertEqual(proposal.agent_run_id, expected.agent_run)
                    # agent-flow-run-guards (AGT-01): the run is a real one, of the key and
                    # the agent that filed the proposal, as the create path requires.
                    assert proposal.agent_run_id is not None
                    run = AgentRun.objects.get(pk=proposal.agent_run_id)
                    self.assertEqual(
                        (run.api_key_id, run.agent_id),
                        (proposal.proposed_by_api_key_id, proposal.proposed_by_agent_id),
                    )

    def test_no_proposal_waits_on_the_research_payment_obligation(self) -> None:
        """Its own version 2 is already filed from the fixture (apps/library/seeds/library.py),
        so a proposal here would apply a redundant version 3 over the one PRO-S3's design card
        and the inventory journeys expect. It carries the seeded problem report instead."""
        seed_e2e()
        self.assertFalse(Proposal.objects.filter(
            target_id=Obligation.objects.get(stable_key=EXPECTED_LIBRARY.research_obligation).id,
            status=ProposalStatus.OPEN.value,
        ).exists())

    def test_the_bank_holds_one_open_problem_report_of_its_own(self) -> None:
        """AUD-S5 (AUD-03): a reader of tenant A said a library record looks wrong. The row
        carries their bank, so no other bank and no platform session reads it, and it stays
        open for the journey that answers it."""
        counts = seed_e2e()
        self.assertEqual(counts["problem_reports"], 1)
        expected = EXPECTED_PROBLEM_REPORT
        tenant_a = Tenant.objects.get(slug=expected.tenant_slug)
        tenancy.activate(tenant_a.id)
        report = ProblemReport.objects.get(tenant=tenant_a)
        self.assertEqual(report.status, ReportStatus.OPEN.value)
        self.assertEqual(report.reporter.email, expected.reporter_email)
        self.assertEqual(report.subject_id, Obligation.objects.get(stable_key=expected.obligation).id)
        self.assertEqual((report.version_number, report.language_id), (expected.version_number, expected.language))
        self.assertTrue(report.text.strip(), "a report says what looks wrong")
        # The words the reader wrote stay in the row: the audit trail carries the record and
        # the report's id, never the text (playbook 4.7).
        audited = AuditEvent.objects.get(action="library.problem_reported", tenant=tenant_a)
        self.assertEqual(audited.after["reportId"], str(report.id))
        self.assertNotIn(report.text, audited.summary)
        # Tenant B is another bank: row-level security shows it nothing of this.
        tenancy.activate(Tenant.objects.get(slug=TENANT_B_SLUG).id)
        self.assertEqual(ProblemReport.objects.count(), 0)

    def test_a_reseed_leaves_the_same_waiting_proposals_and_the_same_report(self) -> None:
        seed_e2e()
        tenant_a = Tenant.objects.get(slug=EXPECTED_PROBLEM_REPORT.tenant_slug)
        tenancy.activate(tenant_a.id)
        proposals = sorted(str(row) for row in Proposal.objects.values_list("id", flat=True))
        reports = sorted(str(row) for row in ProblemReport.objects.values_list("id", flat=True))

        seed_e2e()

        tenancy.activate(tenant_a.id)
        self.assertEqual(sorted(str(row) for row in Proposal.objects.values_list("id", flat=True)), proposals)
        self.assertEqual(sorted(str(row) for row in ProblemReport.objects.values_list("id", flat=True)), reports)

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
        # once tenant A is the one activated. Filtered to chunk 6's own two stable keys,
        # not a bare count: chunk 5's own changes (c5-seed-watch) fan out to every active
        # tenant too, so tenant B's total case count is no longer just these two.
        second_bank = Tenant.objects.get(slug=TENANT_B_SLUG)
        tenancy.activate(second_bank.id)
        self.assertEqual(ChangeCase.objects.filter(change__stable_key__startswith="chg-e2e-tenant-b").count(), 2)
        tenancy.activate(tenant.id)
        self.assertEqual(ChangeCase.objects.filter(change__stable_key__startswith="chg-e2e-tenant-b").count(), 0)

    def _all_tenants_case_count(self) -> int:
        """`ChangeCase` is a `TenantModel` under forced row-level security, so a bare
        `.count()` with no tenant activated reads zero rows in every zone rather than the
        whole table: this sums each seeded tenant's own count instead (proven to fail
        2026-09-21: `assertGreater(cases, 0)` read 0 not greater than 0 with no tenant
        active)."""
        total = 0
        for tenant in Tenant.objects.all():
            tenancy.activate(tenant.id)
            total += ChangeCase.objects.count()
        return total

    def test_chunk_6_seed_is_idempotent(self) -> None:
        seed_e2e()
        cases, checks, changes, briefings = (
            self._all_tenants_case_count(),
            SourceCheck.objects.count(),
            RegulatoryChange.objects.filter(stable_key__startswith="chg-e2e-").count(),
            Briefing.objects.count(),
        )
        self.assertGreater(cases, 0)

        seed_e2e()

        self.assertEqual(self._all_tenants_case_count(), cases)
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

    def test_chunk5_seeds_the_timeline_change_with_its_mixed_precision_dates_and_one_confirmed_term(self) -> None:
        """c5-seed-watch (WAT-S2): named here so a later change to the seed cannot quietly
        hollow out `c5-e2e-watch-journeys-a`'s WAT-S2 and WAT-S9 journeys without failing
        this guard."""
        seed_e2e()
        change = RegulatoryChange.objects.get(stable_key=EXPECTED_CHUNK5_WATCH.timeline_change)
        events = {event.label: event for event in ChangeEvent.objects.filter(change=change)}
        self.assertEqual(events["Consultation opened"].event_date, datetime.date(2026, 3, 1))
        self.assertEqual(events["Consultation opened"].date_precision, "month")
        self.assertEqual(events["Adopted"].event_date, datetime.date(2026, 6, 15))
        self.assertEqual(events["Adopted"].date_precision, "day")
        self.assertEqual(events["In force"].event_date, datetime.date(2027, 1, 1))
        self.assertEqual(events["In force"].date_precision, "quarter")

        # The one confirmed classification, so both suggested and confirmed states render
        # (WAT-S4's confirming half is the held `c5-watch-curation-confirm`, but a seed may
        # write the confirmation columns directly, exactly as `_seed_case`'s So what does).
        term_link = ChangeTerm.objects.get(change=change, term__isnull=False)
        self.assertFalse(term_link.suggested)
        self.assertIsNotNone(term_link.confirmed_by_id)
        self.assertIsNotNone(term_link.confirmed_at)
        flag_link = ChangeTerm.objects.get(change=change, flag__isnull=False)
        self.assertTrue(flag_link.suggested, "the flag is left a suggestion so a suggested pill has something to render too")

    def test_chunk5_seeds_the_obligations_change_with_its_documents_and_links(self) -> None:
        """c5-seed-watch (WAT-S6, AGT-07): named here so a later change to the seed cannot
        quietly hollow out `c5-e2e-watch-journeys-b`'s WAT-S6 journey without failing this
        guard, whether or not it is un-fixme'd yet."""
        seed_e2e()
        change = RegulatoryChange.objects.get(stable_key=EXPECTED_CHUNK5_WATCH.obligations_change)
        documents = ChangeDocument.objects.filter(change=change)
        self.assertEqual(documents.count(), 2)
        self.assertTrue(documents.filter(is_duplicate=True, risk_flags__len__gt=0).exists())

        confirmed = ChangeObligation.objects.get(change=change, obligation__stable_key=CONFIRMED_LINK_OBLIGATION)
        self.assertIsNotNone(confirmed.confirmed_by_id)
        suggested = ChangeObligation.objects.get(change=change, obligation__stable_key=SUGGESTED_LINK_OBLIGATION)
        self.assertIsNone(suggested.confirmed_by_id)

    def test_the_watch_sweeper_key_holds_platform_runs_by_status_and_a_recheck(self) -> None:
        """c5-seed-watch (AGT-01, item 3): the sweeper's platform key carries chunk 5's closed
        run, its open run and the open run each agent proposal it files is attached to,
        counted per status so an extra or a missing run cannot hide behind another of the
        same status; none of them belongs to a bank. A `recheck` line sits beside the sweep
        lines so the coverage log can tell the two apart."""
        seed_e2e()
        key = ApiKey.objects.get(name="Watch sweeper (E2E)")
        self.assertIsNone(key.tenant_id)
        assert key.agent is not None
        self.assertEqual(key.agent.key, "watch-sweeper")
        runs = AgentRun.objects.filter(api_key=key)
        self.assertEqual(Counter(runs.values_list("status", flat=True)), EXPECTED_SWEEPER_RUNS)
        self.assertFalse(runs.filter(tenant_id__isnull=False).exists())
        proposal_runs = {expected.agent_run for expected in EXPECTED_PROPOSALS if expected.agent_run is not None}
        self.assertEqual(len(proposal_runs), 4)
        self.assertLessEqual(proposal_runs, set(runs.filter(status="running").values_list("id", flat=True)))

        recheck = SourceCheck.objects.get(kind=SourceCheckKind.RECHECK.value, source__name=EXPECTED_CHUNK5_WATCH.healthy_source)
        self.assertEqual(recheck.subject_id, Obligation.objects.get(stable_key=RECHECK_OBLIGATION).id)

    def test_chunk5_seeds_both_tenants_cases_with_one_so_what_confirmed_and_one_not(self) -> None:
        """c5-seed-watch (WAT-S7, CAS-01): every active bank gets a case for chunk 5's own
        changes through the real creation path, and tenant A's So what is confirmed while
        tenant B's is still the library's draft, so `c5-e2e-watch-journeys-b`'s WAT-S7
        journey has both states to read."""
        seed_e2e()
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenant_b = Tenant.objects.get(slug=TENANT_B_SLUG)
        for stable_key in (
            EXPECTED_CHUNK5_WATCH.timeline_change,
            EXPECTED_CHUNK5_WATCH.obligations_change,
            EXPECTED_CHUNK5_WATCH.payments_change,
        ):
            with self.subTest(change=stable_key):
                tenancy.activate(tenant_a.id)
                self.assertTrue(ChangeCase.objects.filter(tenant=tenant_a, change__stable_key=stable_key).exists())
                tenancy.activate(tenant_b.id)
                self.assertTrue(ChangeCase.objects.filter(tenant=tenant_b, change__stable_key=stable_key).exists())

        tenancy.activate(tenant_a.id)
        case_a = ChangeCase.objects.get(tenant=tenant_a, change__stable_key=EXPECTED_CHUNK5_WATCH.timeline_change)
        self.assertTrue(case_a.so_what_confirmed)
        tenancy.activate(tenant_b.id)
        case_b = ChangeCase.objects.get(tenant=tenant_b, change__stable_key=EXPECTED_CHUNK5_WATCH.timeline_change)
        self.assertFalse(case_b.so_what_confirmed)

    def test_chunk5_seed_is_idempotent(self) -> None:
        seed_e2e()
        changes = RegulatoryChange.objects.filter(stable_key__startswith="chg-e2e-c5-").count()
        events = ChangeEvent.objects.count()
        documents = ChangeDocument.objects.count()
        term_links = ChangeTerm.objects.count()
        obligation_links = ChangeObligation.objects.count()
        sources = Source.objects.count()
        runs = AgentRun.objects.count()
        keys = ApiKey.objects.count()
        tenancy.activate(Tenant.objects.get(slug=TENANT_A_SLUG).id)
        cases = ChangeCase.objects.count()
        self.assertGreater(changes, 0)

        seed_e2e()

        self.assertEqual(RegulatoryChange.objects.filter(stable_key__startswith="chg-e2e-c5-").count(), changes)
        self.assertEqual(ChangeEvent.objects.count(), events)
        self.assertEqual(ChangeDocument.objects.count(), documents)
        self.assertEqual(ChangeTerm.objects.count(), term_links)
        self.assertEqual(ChangeObligation.objects.count(), obligation_links)
        self.assertEqual(Source.objects.count(), sources)
        self.assertEqual(AgentRun.objects.count(), runs)
        self.assertEqual(ApiKey.objects.count(), keys)
        tenancy.activate(Tenant.objects.get(slug=TENANT_A_SLUG).id)
        self.assertEqual(ChangeCase.objects.count(), cases)

    # --- FP-01, D-36: no seeded bank follows a standard -------------------------------------
    def test_no_seeded_bank_follows_a_standard(self) -> None:
        """No E2E tenant's regulatory scope holds a term of an opt-in dimension, so a
        standard's records start outside every seeded bank's scope, and a journey that opts a
        bank in starts from "none followed" (STD-06). Checked on the expected list and on the
        stored rows."""
        seed_e2e()
        opt_in = opt_in_dimensions()
        self.assertIn("standard", opt_in)
        for slug, refs in EXPECTED_FOOTPRINTS.items():
            with self.subTest(tenant=slug):
                self.assertEqual([ref for ref in refs if ref.split(":")[0] in opt_in], [])
                tenant = Tenant.objects.get(slug=slug)
                tenancy.activate(tenant.id)
                self.assertFalse(FootprintTerm.objects.filter(tenant=tenant, term__dimension__key__in=opt_in).exists())

    # --- lib-standard-e2e-seed (INV-S11, FP-S16) -------------------------------------------
    def test_the_e2e_standard_is_public_facts_and_one_duty_on_the_standards_term(self) -> None:
        """INV-08, D-35, D-36: seed_e2e files ISO/IEC 27001:2022 under International and
        ISO/IEC with no provision and exactly one duty, whose one term is the standard's.
        No seeded bank follows the term, so none sees the duty in its inventory. That the
        prototype seed_demo loads holds no standard is check_prototype_data's to refuse."""
        seed_e2e()
        standard = Instrument.objects.select_related("level", "jurisdiction", "authority", "regime").get(stable_key=E2E_STANDARD_INSTRUMENT)
        self.assertEqual(
            (standard.level.kind, standard.jurisdiction.key, standard.authority.key if standard.authority else None, standard.regime.key),
            ("standard", "intl", "iso-iec", "ai_ict"),
        )
        self.assertEqual((standard.official_ref, standard.binding, standard.provisions.count()), ("ISO/IEC 27001:2022", False, 0))
        # No official title anywhere: the edition is titled by its reference alone.
        self.assertEqual(list(standard.titles.values_list("text", flat=True)), ["ISO/IEC 27001:2022"])
        duty = Obligation.objects.get(instrument=standard)
        self.assertEqual((duty.stable_key, duty.ref_label), (E2E_STANDARD_OBLIGATION, standard.official_ref))
        self.assertEqual([(t.dimension.key, t.key, t.active) for t in duty.terms.select_related("dimension")], [("standard", "iso_iec_27001", True)])
        self.assertFalse(Instrument.objects.filter(level__kind="standard").exclude(pk=standard.pk).exists())
        restricting = restricting_dimensions()
        for tenant in Tenant.objects.order_by("slug"):
            with self.subTest(tenant=tenant.slug):
                tenancy.activate(tenant.id)
                self.assertFalse(in_footprint(_scope(duty), footprint_of(tenant.id), restricting=restricting))
    # --- end lib-standard-e2e-seed ---------------------------------------------------------

    # --- std-journeys (FP-S16) ------------------------------------------------------------
    def test_e2e_switches_the_standard_on_and_logs_it_once(self) -> None:
        """FP-S16 (FP-01, INV-08, D-8x std-journeys): a scope request names active terms only,
        so seed_e2e switches ISO/IEC 27001 on for E2E alone, with one version bump and one
        audit row, and a second run changes nothing. The reference seed keeps it off
        everywhere else (apps/taxonomy/tests_matching.HeldStandard)."""
        seed_e2e()
        term = TaxonomyTerm.objects.get(dimension__key="standard", key="iso_iec_27001")
        self.assertTrue(term.active)
        events = AuditEvent.objects.filter(action="taxonomy.term_updated", subject_id=term.id)
        self.assertEqual([(e.before, e.after, e.actor_label) for e in events], [({"active": False}, {"active": True}, "seed_reference")])
        version = term.version
        seed_e2e()
        term.refresh_from_db()
        self.assertEqual((term.active, term.version, events.count()), (True, version, 1))
    # --- end std-journeys -------------------------------------------------------------------

    # --- library-updates-frontend (PRO-S7) ---------------------------------------------
    def test_the_obligation_pro_s7_approves_reaches_tenant_a_with_or_without_advice(self) -> None:
        """PRO-S7 (PRO-03): the officer finds the approved change on "Library updates", which
        lists only what reaches the bank's footprint. J-6 switches Advice off while other
        journeys run, so the duty has to reach tenant A either way, and it has to be on
        version 1 so the approval writes a clean version 2."""
        seed_e2e()
        self.assertEqual(next(expected.target for expected in EXPECTED_PROPOSALS if expected.journey == "PRO-S7"), PRO_S7_OBLIGATION)
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        footprint = footprint_of(tenant_a.id)
        without = {dimension: set(keys) for dimension, keys in footprint.items()}
        for ref in EXPECTED_PENDING_REQUEST.removes:
            dimension, key = ref.split(":")
            without[dimension].discard(key)
        obligation = (
            Obligation.objects.select_related("instrument__regime__dimension")
            .prefetch_related("terms__dimension")
            .get(stable_key=PRO_S7_OBLIGATION)
        )
        restricting = restricting_dimensions()
        self.assertTrue(in_footprint(_scope(obligation), footprint, restricting=restricting))
        self.assertTrue(in_footprint(_scope(obligation), without, restricting=restricting))
        self.assertEqual(list(ObligationVersion.objects.filter(obligation=obligation).values_list("version_number", flat=True)), [1])
    # --- end library-updates-frontend ------------------------------------------------------

    # --- FP-S4 (FP-03, tax-fp-s4-journey) ----------------------------------------------------
    def test_every_seeded_case_carries_the_verdict_the_scope_rule_gives(self) -> None:
        """FP-S4, FP-03: the roadmap and the briefing read the verdict cached on a case, while
        the feed decides it again from the change's scope terms on every read. A seeded case
        whose cache disagrees with the rule is in scope on one surface and out on the other,
        and the first approved footprint change recomputes it and moves it. So every case of
        both banks is checked against the database's own rule, and tenant A's case for the
        outside-scope change is among them and answers false.

        Proven to fail 2026-09-23 with the outside-scope change seeded without its scope
        term: that change matches every bank by the rule, while its case says false."""
        from apps.cases.reading import scope_term_ids_of_each_case

        seed_e2e()
        verdicts: dict[tuple[str, str], bool] = {}
        for tenant in Tenant.objects.order_by("slug"):
            tenancy.activate(tenant.id)
            # The change's whole scope, the jurisdictions its authority reaches included
            # (FP-04), exactly as the recomputation hands it to the rule.
            for case in ChangeCase.objects.select_related("change").annotate(term_ids=scope_term_ids_of_each_case()):
                with self.subTest(tenant=tenant.slug, change=case.change.stable_key):
                    self.assertEqual(case.footprint_match, in_footprint_sql(tenant.id, case.term_ids))
                verdicts[(tenant.slug, case.change.stable_key)] = case.footprint_match
        self.assertIs(verdicts[(TENANT_A_SLUG, EXPECTED_HOME.outside_scope_change)], False)
        self.assertIs(verdicts[(TENANT_A_SLUG, EXPECTED_HOME.lead_change)], True)

    def test_fp_s4_finds_an_obligation_and_a_change_outside_tenant_a_scope_as_seeded(self) -> None:
        """FP-S4, FP-03: the journey walks tenant A's scope as seeded and never changes it,
        because FP-S5 (J-6) changes that scope and every home and watch journey reads it in
        parallel. So the seed leaves one term out of it on purpose, and one obligation and
        one change fall outside through that term alone. The obligation is neither a seeded
        proposal's target nor one of the seed's named records, the constants other journeys
        find their records by, so none of those needs it in scope."""
        seed_e2e()
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        dimension, key = EXPECTED_OUTSIDE_SCOPE.term.split(":")
        footprint = footprint_of(tenant_a.id)
        self.assertNotIn(key, footprint[dimension], "the scope leaves the term out")
        self.assertIn(dimension, restricting_dimensions(), "and the dimension it sits in narrows the scope")

        obligation = Obligation.objects.select_related("instrument__regime__dimension").get(stable_key=EXPECTED_OUTSIDE_SCOPE.obligation)
        scope = _scope(obligation)
        self.assertIn(key, scope[dimension])
        self.assertFalse(in_footprint(scope, footprint, restricting=restricting_dimensions()))

        change = RegulatoryChange.objects.get(stable_key=EXPECTED_OUTSIDE_SCOPE.change)
        term_ids = list(ChangeTerm.objects.filter(change=change, term__isnull=False).values_list("term_id", flat=True))
        self.assertTrue(ChangeTerm.objects.filter(change=change, term__dimension__key=dimension, term__key=key).exists())
        self.assertFalse(in_footprint_sql(tenant_a.id, term_ids))

        spoken_for = {proposal.target for proposal in EXPECTED_PROPOSALS} | {
            EXPECTED_LIBRARY.advice_only_obligation,
            EXPECTED_LIBRARY.research_obligation,
            EXPECTED_PROBLEM_REPORT.obligation,
            RECHECK_OBLIGATION,
            CONFIRMED_LINK_OBLIGATION,
            SUGGESTED_LINK_OBLIGATION,
        }
        self.assertNotIn(
            EXPECTED_OUTSIDE_SCOPE.obligation,
            spoken_for,
            "FP-S4 keeps this obligation outside tenant A's scope: point the proposal or record that names it at one that stays inside",
        )

    # --- tax-nordic-seed (FP-04, FP-S10) ---------------------------------------------------
    def test_tenant_a_watches_denmark_through_the_audited_write_and_tenant_b_nothing(self) -> None:
        """FP-S10, FP-04: the seed watches a market through markets_logic.watch(), the write
        the product makes, so each watch leaves one `markets.watch_added` audit row; a reseed
        adds neither a row nor an audit event."""
        seed_e2e()
        seed_e2e()
        for slug, keys in EXPECTED_WATCHED_MARKETS.items():
            with self.subTest(tenant=slug):
                tenant = Tenant.objects.get(slug=slug)
                tenancy.activate(tenant.id)
                watched = WatchedMarket.objects.filter(tenant=tenant)
                self.assertEqual(sorted(watched.values_list("jurisdiction__key", flat=True)), sorted(keys))
                audited = AuditEvent.objects.filter(tenant=tenant, action="markets.watch_added")
                self.assertEqual(sorted(audited.values_list("subject_title", flat=True)), sorted(keys))
        self.assertEqual(EXPECTED_WATCHED_MARKETS[TENANT_A_SLUG], ("dk",))
        self.assertEqual(EXPECTED_WATCHED_MARKETS[TENANT_B_SLUG], ())

    # --- tax-watched-feed (FP-04, FP-S15) ---------------------------------------------------
    def test_the_danish_custody_change_is_outside_tenant_a_scope_and_from_a_market_it_watches(self) -> None:
        """FP-S15, FP-04: tenant A operates in Sweden and watches Denmark, so the Danish
        authority's custody change is outside its scope by jurisdiction alone, and its case,
        opened by the real fan-out, says so. It moves neither the lead nor this week: the
        lowest urgency, first seen last week. A reseed opens no second case."""
        from apps.shared.e2e_seed import EXPECTED_WATCHED_CHANGE

        seed_e2e()
        seed_e2e()
        change = RegulatoryChange.objects.select_related("authority__jurisdiction").get(stable_key=EXPECTED_WATCHED_CHANGE)
        self.assertEqual(change.authority.jurisdiction.key if change.authority else None, "dk")
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        self.assertIn("se", footprint_of(tenant_a.id)["jurisdiction"])
        case = ChangeCase.objects.get(change=change)
        self.assertEqual((case.footprint_match, case.urgency.key, case.urgency_confirmed), (False, "monitor", False))
        self.assertLess(change.first_seen_at, ChangeCase.objects.get(change__stable_key=EXPECTED_HOME.lead_change).change.first_seen_at)

    def test_the_library_holds_a_danish_and_a_norwegian_supervisor_and_act(self) -> None:
        """FP-04: the markets journeys need Danish and Norwegian rules. Each country has its
        financial supervisory authority and one act under a regime term, with a dated
        in-force precision, and between them obligations for Custody and for Advice that
        match tenant A's scope in every dimension but jurisdiction (`_scope()` derives none):
        tenant A operates in Sweden, so what reaches it from Denmark is what watching adds."""
        seed_e2e()
        for key, country in (("finanstilsynet-dk", "dk"), ("finanstilsynet-no", "no")):
            with self.subTest(authority=key):
                self.assertEqual(Authority.objects.get(key=key).jurisdiction.key, country)
        services: set[str] = set()
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        footprint = footprint_of(tenant_a.id)
        restricting = restricting_dimensions()
        for country in ("dk", "no"):
            with self.subTest(jurisdiction=country):
                instrument = Instrument.objects.select_related("regime__dimension").get(jurisdiction__key=country)
                self.assertEqual(instrument.regime.dimension.key, "regime")
                self.assertIsNotNone(instrument.in_force_from)
                self.assertEqual(instrument.in_force_from_precision, DatePrecision.DAY.value)
                obligations = Obligation.objects.filter(instrument=instrument).select_related("instrument__regime__dimension").prefetch_related("terms__dimension")
                self.assertTrue(obligations.exists())
                for obligation in obligations:
                    self.assertTrue(in_footprint(_scope(obligation), footprint, restricting=restricting), obligation.stable_key)
                    services |= _scope(obligation).get("service_type", set())
        self.assertLessEqual({"custody", "advice"}, services)

    def test_the_seed_starts_from_an_empty_mock_outbox(self) -> None:
        """The mock outbox is one cache entry that never expires, and an E2E run recreates the
        database but not the cache, so a journey could read an earlier run's mail. The seed
        empties it before anything else; a reseed sends nothing of its own, so after one the
        outbox is empty."""
        seed_e2e()
        earlier = OutgoingMail(to="earlier-run@example-bank.test", subject="An earlier run", body="An earlier run")
        MockMailer().send(earlier)
        self.assertIn(earlier, MockMailer.sent)
        seed_e2e()
        self.assertEqual(MockMailer.sent, [])
    # --- end tax-nordic-seed -----------------------------------------------------------------

    def test_every_seeded_change_carries_a_regime(self) -> None:
        """D-39, AC-AGT1: `createChange` refuses a change with no regime term, so no seeded
        change may be one the route would never have stored (watch-regime-required)."""
        seed_e2e()
        without = RegulatoryChange.objects.exclude(term_links__term__dimension__key="regime").values_list("stable_key", flat=True)
        self.assertEqual(list(without), [], "every seeded change names a term of the regime dimension")

    # --- tax-watched-inventory (FP-04, FP-S13) -------------------------------------------------
    def test_tenant_a_markets_we_watch_view_holds_the_danish_custody_rule(self) -> None:
        """FP-S13's journey reads tenant A as seeded: operating in Sweden, providing Custody
        and watching Denmark. So "Markets we watch" lists the Danish custody obligation and its
        act and nothing from another market; the Norwegian rule, whose market nobody watches,
        is not there and is outside the scope; the default view hides the Danish one."""
        from apps.library.reading import in_view

        seed_e2e()
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        self.assertIn("jurisdiction:se", EXPECTED_FOOTPRINTS[TENANT_A_SLUG])
        self.assertEqual(EXPECTED_WATCHED_MARKETS[TENANT_A_SLUG], ("dk",))
        watched = in_view(Obligation.objects.all(), tenant_a, "watched")
        self.assertIn(WATCHED_MARKET_OBLIGATION, set(watched.values_list("stable_key", flat=True)))
        self.assertEqual(set(watched.values_list("instrument__jurisdiction__key", flat=True)), {"dk"})
        self.assertEqual(set(in_view(Instrument.objects.all(), tenant_a, "watched").values_list("jurisdiction__key", flat=True)), {"dk"})
        norwegian = Obligation.objects.filter(instrument__jurisdiction__key="no")
        self.assertTrue(norwegian.exists())
        self.assertFalse(in_view(norwegian, tenant_a, "in").exists())
        self.assertFalse(in_view(Obligation.objects.filter(stable_key=WATCHED_MARKET_OBLIGATION), tenant_a, "in").exists())
    # --- end tax-watched-inventory -------------------------------------------------------------

    # --- tax-market-journeys (FP-S8, TEN-S7) --------------------------------------------------
    def test_fp_s8_has_two_people_in_tenant_b_and_one_obligation_per_jurisdiction(self) -> None:
        """FP-S8: tenant B's admin requests and a second tenant-B login with a passkey approves
        (four eyes); B's scope names no jurisdiction, so turning Denmark on is the change. As
        seeded the journey's three obligations are in B's scope; with Denmark added the EU
        and Danish ones still are and the Swedish one is not."""
        from apps.library import reading
        from apps.shared.e2e_seed import EXPECTED_MARKET_JOURNEY as spec
        from apps.shared.permissions import FOOTPRINT_APPROVE, FOOTPRINT_REQUEST

        seed_e2e()
        tenant = Tenant.objects.get(slug=spec.tenant_slug)
        tenancy.activate(tenant.id)
        requester = Membership.objects.get(tenant=tenant, user__email=spec.requester_email)
        approver = Membership.objects.get(tenant=tenant, user__email=spec.approver_email)
        self.assertNotEqual(requester.user_id, approver.user_id)
        self.assertIn(FOOTPRINT_REQUEST, {p for role in requester.roles.all() for p in role.permissions})
        approver_permissions = {p for role in approver.roles.all() for p in role.permissions}
        self.assertIn(FOOTPRINT_APPROVE, approver_permissions)
        self.assertNotIn(FOOTPRINT_REQUEST, approver_permissions)
        for membership in (requester, approver):
            self.assertIn(membership.user.email, E2E_PASSKEYS)
            self.assertTrue(WebAuthnCredential.objects.filter(user=membership.user).exists())

        footprint = footprint_of(tenant.id)
        self.assertNotIn("jurisdiction", footprint)
        restricting = restricting_dimensions()
        keys = {"eu": spec.union_obligation, "se": spec.home_obligation, spec.country: spec.country_obligation}
        obligations = {o.stable_key: o for o in Obligation.objects.select_related("instrument__jurisdiction").filter(stable_key__in=keys.values())}
        scopes = reading.obligation_scopes([o.id for o in obligations.values()])
        with_country = {**footprint, "jurisdiction": {spec.country}}
        for jurisdiction, key in keys.items():
            with self.subTest(obligation=key):
                obligation = obligations[key]
                self.assertEqual(obligation.instrument.jurisdiction.key, jurisdiction)
                scope = {dimension: {t.key for t in terms} for dimension, terms in scopes[obligation.id].items()}
                self.assertTrue(in_footprint(scope, footprint, restricting=restricting))
                self.assertEqual(in_footprint(scope, with_country, restricting=restricting), jurisdiction != "se")

    def test_tenant_a_has_a_role_and_a_tag_tenant_b_does_not(self) -> None:
        """TEN-S7 (J-8): the custom role and tenant tag the journey looks for in B are A's
        alone, and a reseed writes neither again."""
        from apps.identity.models import TenantRole

        spec = EXPECTED_TENANT_A_ONLY
        from apps.taxonomy.tenant_lists_logic import entry_for

        seed_e2e()
        seed_e2e()
        tags = entry_for(spec.tag_list).model._default_manager
        for tenant in Tenant.objects.all():
            with self.subTest(tenant=tenant.slug):
                tenancy.activate(tenant.id)
                expected = 1 if tenant.slug == spec.tenant_slug else 0
                self.assertEqual(TenantRole.objects.filter(tenant=tenant, key=spec.role_key).count(), expected)
                self.assertEqual(tags.filter(tenant=tenant, key=spec.tag_key).count(), expected)
    # --- end tax-market-journeys ---------------------------------------------------------------

    # --- lib-machine-confirmed-journey (INV-S14) -------------------------------------------
    def test_inv_s14_finds_a_record_agents_confirmed_and_one_a_person_re_verified_since(self) -> None:
        """INV-S14 (INV-05, INV-06, PRO-02, D-74): two records whose version in force was filed
        by the watch sweeper in its own run and approved by the library confirmer, a second
        definition with a key and a run of its own, its model call logged. The second record
        was then re-verified by a named platform person, strictly after the approval even at
        the millisecond a screen compares, so its label gives way and the first one's never
        does. Both sit inside tenant A's scope and no other journey names them."""
        seed_e2e()
        expected = EXPECTED_MACHINE_CONFIRMED
        editor = User.objects.get(email=expected.reverifier_email)
        for stable_key in (expected.machine_confirmed, expected.reverified):
            with self.subTest(record=stable_key):
                obligation = Obligation.objects.select_related("verified_by").get(stable_key=stable_key)
                version = ObligationVersion.objects.select_related("verified_by_agent", "applied_by_proposal__proposed_by_agent").filter(obligation=obligation).order_by("-version_number").first()
                assert version is not None and version.applied_by_proposal is not None and version.approved_at is not None
                proposal = version.applied_by_proposal
                self.assertEqual(version.verified_origin, "agent")
                self.assertEqual(getattr(version.verified_by_agent, "key", None), "library-confirmer")
                self.assertEqual(getattr(proposal.proposed_by_agent, "key", None), "watch-sweeper")
                self.assertEqual(proposal.status, ProposalStatus.APPROVED.value)
                self.assertIsNone(proposal.reviewed_by_id, "no person approved it")
                self.assertEqual(getattr(proposal.reviewed_by_agent, "key", None), "library-confirmer")
                self.assertIsNone(version.effective_from, "in force whatever date a screen reads it as of")
                decision = AiGeneration.objects.get(purpose="agent_review", subject_id=proposal.id)
                assert decision.agent_run is not None
                self.assertEqual(decision.agent_run.agent.key, "library-confirmer")
                self.assertEqual(decision.agent_run.api_key_id, proposal.reviewed_by_api_key_id, "decided in a run of the deciding key")
                self.assertNotEqual(proposal.reviewed_by_api_key_id, proposal.proposed_by_api_key_id, "the confirmer used a key of its own")
                if stable_key == expected.reverified:
                    self.assertEqual(obligation.verified_by, editor)
                    assert obligation.last_verified_at is not None
                    stamped_ms, approved_ms = (int(moment.timestamp() * 1000) for moment in (obligation.last_verified_at, version.approved_at))
                    self.assertGreater(stamped_ms, approved_ms)
                else:
                    self.assertIsNone(obligation.verified_by, "nobody has re-verified it since")

        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        footprint = footprint_of(tenant_a.id)
        for stable_key in (expected.machine_confirmed, expected.reverified):
            obligation = Obligation.objects.select_related("instrument__regime__dimension").get(stable_key=stable_key)
            self.assertTrue(in_footprint(_scope(obligation), footprint, restricting=restricting_dimensions()), stable_key)
        spoken_for = {proposal.target for proposal in EXPECTED_PROPOSALS} | {
            EXPECTED_LIBRARY.advice_only_obligation,
            EXPECTED_LIBRARY.research_obligation,
            EXPECTED_PROBLEM_REPORT.obligation,
            EXPECTED_OUTSIDE_SCOPE.obligation,
            RECHECK_OBLIGATION,
            CONFIRMED_LINK_OBLIGATION,
            SUGGESTED_LINK_OBLIGATION,
        }
        self.assertEqual({expected.machine_confirmed, expected.reverified} & spoken_for, set())

    def test_inv_s14_reseed_changes_nothing(self) -> None:
        seed_e2e()
        counts = (Proposal.objects.count(), ObligationVersion.objects.count(), Verification.objects.count(), AgentRun.objects.count(), ApiKey.objects.count(), AiGeneration.objects.count())
        seed_e2e()
        self.assertEqual(
            (Proposal.objects.count(), ObligationVersion.objects.count(), Verification.objects.count(), AgentRun.objects.count(), ApiKey.objects.count(), AiGeneration.objects.count()),
            counts,
        )

    # --- pro-s13-journey (PRO-S13) -------------------------------------------------------------
    def test_pro_s13_finds_a_sweeper_proposal_of_its_own_for_the_confirming_agent(self) -> None:
        """PRO-S13 (PRO-01, PRO-02, AGT-01): the confirming agent decides a proposal the
        watch-sweeper filed through its own key, as the create route files an agent's: the
        proposal names the sweeper's agent and key, its run is that key's, and its audit row
        names the agent as the actor, never a bare run or key. The target is on version 1
        and reaches tenant A with or without Advice, so the reader finds a clean version 2
        on the card whichever way J-6 has left the scope; no other seeded proposal or named
        record sits on it."""
        seed_e2e()
        expected = next(row for row in EXPECTED_PROPOSALS if row.journey == "PRO-S13")
        self.assertEqual((expected.target, expected.agent_run, expected.proposed_by_email), (PRO_S13_OBLIGATION, PRO_S13_RUN, ""))
        others = {row.target for row in EXPECTED_PROPOSALS if row.journey != "PRO-S13"} | {
            EXPECTED_LIBRARY.advice_only_obligation,
            EXPECTED_LIBRARY.research_obligation,
            EXPECTED_PROBLEM_REPORT.obligation,
            EXPECTED_OUTSIDE_SCOPE.obligation,
            RECHECK_OBLIGATION,
            CONFIRMED_LINK_OBLIGATION,
            SUGGESTED_LINK_OBLIGATION,
        }
        self.assertNotIn(PRO_S13_OBLIGATION, others)

        tenancy.clear_tenant()
        (proposal,) = _waiting_for(expected)
        assert proposal.proposed_by_agent is not None and proposal.proposed_by_api_key_id is not None
        self.assertEqual(proposal.proposed_by_agent.key, "watch-sweeper")
        self.assertIsNone(proposal.proposed_by_user)
        key = ApiKey.objects.get(pk=proposal.proposed_by_api_key_id)
        self.assertEqual((key.agent_id, key.tenant_id), (proposal.proposed_by_agent_id, None))
        run = AgentRun.objects.get(pk=PRO_S13_RUN)
        self.assertEqual((run.api_key_id, run.agent_id), (key.id, proposal.proposed_by_agent_id))
        created = AuditEvent.objects.get(subject_id=proposal.id, action="proposal.created")
        self.assertEqual((created.actor_type, created.actor_id), ("agent", proposal.proposed_by_agent_id))

        obligation = (
            Obligation.objects.select_related("instrument__regime__dimension")
            .prefetch_related("terms__dimension")
            .get(stable_key=PRO_S13_OBLIGATION)
        )
        self.assertEqual(list(ObligationVersion.objects.filter(obligation=obligation).values_list("version_number", flat=True)), [1])
        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        footprint = footprint_of(tenant_a.id)
        without = {dimension: set(keys) for dimension, keys in footprint.items()}
        for ref in EXPECTED_PENDING_REQUEST.removes:
            dimension, term = ref.split(":")
            without[dimension].discard(term)
        restricting = restricting_dimensions()
        self.assertTrue(in_footprint(_scope(obligation), footprint, restricting=restricting))
        self.assertTrue(in_footprint(_scope(obligation), without, restricting=restricting))
    # --- end pro-s13-journey -------------------------------------------------------------------

    # --- watch-standards (WAT-S10) ---------------------------------------------------------
    def test_the_standards_change_reaches_tenant_a_only_while_the_journey_has_it_follow(self) -> None:
        """WAT-S10's journey data: the amendment is named by its reference alone, issued by
        a standards body, and seen by no seeded bank until `e2e_follow_standard on`; `off`
        puts tenant A's scope and the case's verdict back as seeded."""
        seed_e2e()
        spec = EXPECTED_STANDARD_CHANGE
        change = RegulatoryChange.objects.select_related("authority__jurisdiction").get(stable_key=spec.stable_key)
        self.assertEqual((change.title, change.key_date_label), (spec.title, spec.key_date_label))
        assert change.authority is not None
        self.assertEqual(change.authority.jurisdiction.kind, "international")
        self.assertEqual(
            sorted(
                f"{dimension}:{key}"
                for dimension, key in change.term_links.filter(term__isnull=False).values_list("term__dimension__key", "term__key")
            ),
            ["regime:ai_ict", spec.term],
        )
        self.assertEqual([event.label for event in change.events.order_by("sort_order")], ["Draft for comment", "Published"])

        def verdicts() -> dict[str, bool]:
            found = {}
            for tenant in Tenant.objects.order_by("slug"):
                tenancy.activate(tenant.id)
                found[tenant.slug] = ChangeCase.objects.get(change=change).footprint_match
            tenancy.clear_tenant()
            return found

        def follows() -> bool:
            tenancy.activate(Tenant.objects.get(slug=TENANT_A_SLUG).id)
            held = FootprintTerm.objects.filter(term__dimension__key="standard").exists()
            tenancy.clear_tenant()
            return held

        self.assertEqual(verdicts(), {TENANT_A_SLUG: False, TENANT_B_SLUG: False})
        call_command("e2e_follow_standard", "on", stdout=StringIO())
        self.assertTrue(follows())
        self.assertEqual(verdicts(), {TENANT_A_SLUG: True, TENANT_B_SLUG: False})
        call_command("e2e_follow_standard", "off", stdout=StringIO())
        self.assertFalse(follows())
        self.assertEqual(verdicts(), {TENANT_A_SLUG: False, TENANT_B_SLUG: False})

    @override_settings(IS_DEPLOYED_ENVIRONMENT=True, ENVIRONMENT="production")
    def test_the_standard_toggle_refuses_a_deployed_environment(self) -> None:
        with self.assertRaises(SeedRefused):
            call_command("e2e_follow_standard", "on", stdout=StringIO())
