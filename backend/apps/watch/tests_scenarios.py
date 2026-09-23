"""Scenario stubs for the watch app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: WAT.
"""

import datetime
from typing import Any
from unittest import skip

from django.conf import settings
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.cases import creation, testing as case_build
from apps.cases.models import CaseObligationLink, ChangeCase
from apps.governance.models import AiGeneration
from apps.library import testing as library_build
from apps.shared import factories, outbox, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    sign_in,
    stub_api_key,
    stub_session,
    user_principal,
)
from apps.taxonomy.models import ChangeType, FootprintTerm, TaxonomyTerm
from apps.watch import testing as watch_build
from apps.watch.models import ChangeDocument, ChangeObligation, RegulatoryChange, SourceCheck

# The reform WAT-S3 names, held apart from the field that carries it. A stable key and the
# word "stableKey" on one line read to gitleaks' generic-api-key rule as a credential and
# its value, and the secret scan failed on a scenario fixture (2026-09-21). Allowlisting it
# would have taught the scanner to ignore the shape a real leak takes.
_DORA_RTS = "eu-dora-rts-2026-01"

# One reform as a sweep files it, for the scenarios that register one. A function rather
# than a constant because every change carries a regime (D-39, AC-AGT1), and a term's id is
# known only once the reference seed has run.
def _change() -> dict[str, Any]:
    return {
        "stableKey": "chg-fi-2026-research-payments",
        "title": "FI adopts amended rules on paying for investment research",
        "changeType": "adopted",
        "authorityLabel": "Finansinspektionen",
        "summary": "FI's board decided to amend three regulations in the securities area.",
        "sourceLabel": "Finansinspektionen",
        "sourceUrl": "https://www.fi.se/",
        "documents": [{"url": "https://www.fi.se/en/published/news/2026/research-payments/", "isPrimary": True}],
        "termIds": [str(watch_build.term(_SECURITIES).id)],
    }


# WAT-S6 and WAT-S7 drive two banks over the real routes, so they need the case the
# registration opens and the words a bank writes over the draft.
_SECURITIES = "regime:securities"
_AML = "regime:aml"
_AI_ICT = "regime:ai_ict"
_ISO_27001 = "standard:iso_iec_27001"
_DRAFT = "Teams that pay for external research should confirm that documented criteria exist."
_OUR_WORDS = "Self-directed trading and Guided investing both pay for research; the desk documents the criteria."


def _drain() -> None:
    """Deliver the outbox until it is empty, so the cases the registration opened exist."""
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


class WatchScenarioTests(TestCase):
    """Scenario tests for apps.watch, one method per @integration scenario."""

    def _run_with_a_key(self) -> tuple[Any, str]:
        """A platform key with a run open, and the value it sends as `X-API-Key`."""
        watch_build.seed_watch_reference()
        tenancy.clear_tenant()
        key = agent_build.agent_key()
        return agent_build.platform_run(key=key), key.plain_key

    def _two_banks(self) -> Any:
        """Two banks with different footprints, their cases opened by the real handler."""
        creation.register()
        banks = case_build.two_tenants_with_different_footprints(inside=_SECURITIES, outside=_AML)
        _drain()
        tenancy.clear_tenant()
        return banks

    def _register(self, plain: str, payload: dict[str, Any]) -> Any:
        return self.client.post(
            "/api/v1/changes", data=payload, content_type="application/json", HTTP_X_API_KEY=plain
        )

    def test_wat_s1(self) -> None:
        """WAT-S1

        The source registry and coverage log show what was checked and with what result (WAT-01).
        Operations: `createSource`, `updateSource`, `recordSourceCheck`.
        """
        watch_build.seed_watch_reference()
        tenancy.clear_tenant()
        key = agent_build.agent_key()
        person = factories.platform_user(email="library.editor@bleqq.example")
        editor = stub_session(user_principal(permissions={perms.SOURCES_MANAGE}, subject_id=person.id))
        session: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

        # Given a registered source "Finansinspektionen news" with a check cadence
        with editor:
            registered = self.client.post(
                "/api/v1/sources",
                data={
                    "name": "Finansinspektionen news",
                    "url": "https://www.fi.se/en/published/news/",
                    "kind": "authority_site",
                    "checkFrequency": "daily",
                },
                content_type="application/json",
                **session,
            )
        self.assertEqual(registered.status_code, 201, registered.content)
        self.assertEqual(registered.json()["checkFrequency"], "daily")

        # When an agent run logs a check with status ok and zero new items, and a later one fails
        run = agent_build.platform_run(key=key)
        now = timezone.now()
        first_check_at = now - datetime.timedelta(hours=2)
        for body, at in (
            ({"status": "ok", "itemsFound": 0}, first_check_at),
            ({"status": "failed", "error": "502 from the publisher after three retries"}, now),
        ):
            logged = self.client.post(
                f"/api/v1/agent-runs/{run.id}/source-checks",
                data={"sourceName": "Finansinspektionen news", "checkedAt": at.isoformat(), **body},
                content_type="application/json",
                HTTP_X_API_KEY=key.plain_key,
            )
            self.assertEqual(logged.status_code, 204, logged.content)

        # Then the coverage log lists both with time, result and the run
        logged_checks = list(SourceCheck.objects.order_by("checked_at"))
        self.assertEqual([check.status for check in logged_checks], ["ok", "failed"])
        self.assertEqual([check.items_found for check in logged_checks], [0, 0])
        self.assertEqual({check.agent_run_id for check in logged_checks}, {run.id})
        self.assertEqual([check.checked_at for check in logged_checks], [first_check_at, now])

        # And the console's "Source coverage" shows the source as stale after the failure,
        # with the failing check named
        with stub_session(user_principal(permissions={perms.SOURCES_MANAGE}, subject_id=person.id)):
            coverage = self.client.get("/api/v1/sources/coverage", **session)
        self.assertEqual(coverage.status_code, 200, coverage.content)
        row = coverage.json()[0]
        self.assertEqual(row["source"]["name"], "Finansinspektionen news")
        self.assertTrue(row["overdue"])
        self.assertEqual(row["lastStatus"], "failed")
        self.assertEqual(row["lastError"], "502 from the publisher after three retries")

    def test_wat_s2(self) -> None:
        """WAT-S2

        One record per reform carries a timeline with partial dates (WAT-02).
        Operations: `createChange`, `addChangeEvent`, `updateChangeEvent`.
        """
        run, plain = self._run_with_a_key()

        # Given a change registered with a consultation date of 2026-03, an adoption date
        # of 2026-06-15 and in force "Q1 2027"
        registered = self._register(
            plain,
            {
                **_change(),
                "agentRunId": str(run.id),
                "events": [
                    {"label": "Consultation opened", "eventDate": "2026-03-01", "datePrecision": "month", "sortOrder": 1},
                    {"label": "Adopted", "eventDate": "2026-06-15", "datePrecision": "day", "occurred": True, "sortOrder": 2},
                    {"label": "In force", "eventDate": "2027-01-01", "datePrecision": "quarter", "sortOrder": 3},
                ],
            },
        )
        self.assertEqual(registered.status_code, 201, registered.content)

        # Then one regulatory change row exists with three timeline entries, each with its precision
        change = RegulatoryChange.objects.get()
        self.assertEqual(
            [(event.label, event.event_date, event.date_precision) for event in change.events.all()],
            [
                ("Consultation opened", datetime.date(2026, 3, 1), "month"),
                ("Adopted", datetime.date(2026, 6, 15), "day"),
                ("In force", datetime.date(2027, 1, 1), "quarter"),
            ],
        )
        # The screen renders them from these three facts; a date is a plain date with a
        # precision, never a timestamp, so no day is printed that the source did not state.
        self.assertEqual([type(event.event_date) for event in change.events.all()], [datetime.date] * 3)

    def test_wat_s3(self) -> None:
        """WAT-S3

        A known stableKey merges duplicates and returns the existing change (WAT-02, AC-WAT1).
        Operations: `createChange`, `addChangeDocument`.
        """
        run, plain = self._run_with_a_key()

        # Given a change registered with stableKey "eu-dora-rts-2026-01"
        first = self._register(plain, {**_change(), "stableKey": _DORA_RTS, "agentRunId": str(run.id)})
        self.assertEqual(first.status_code, 201, first.content)

        # When an agent posts the same stableKey with a new source page
        again = self._register(
            plain,
            {
                **_change(),
                "stableKey": _DORA_RTS,
                "agentRunId": str(run.id),
                "documents": [{"url": "https://eur-lex.europa.eu/eli/reg_del/2026/1/oj", "isPrimary": True}],
            },
        )

        # Then the response is 200 with the existing change id
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["id"], first.json()["id"])

        # And the new page is linked as a duplicate document on that change
        pages = {document.url: document for document in ChangeDocument.objects.all()}
        self.assertTrue(pages["https://eur-lex.europa.eu/eli/reg_del/2026/1/oj"].is_duplicate)

        # And no second change row exists
        self.assertEqual(RegulatoryChange.objects.count(), 1)

    @skip("pending: WAT-S4")
    def test_wat_s4(self) -> None:
        """WAT-S4

        Types, flags and scope come from vocabularies and stay suggestions until confirmed (WAT-03).
        """

    def test_wat_s5(self) -> None:
        """WAT-S5

        An unknown key answers unknown_key with the valid keys (WAT-03, AC-WAT2).
        Operations: `updateChange`.
        """
        watch_build.seed_watch_reference()
        change = watch_build.change_with_timeline()
        valid = sorted(ChangeType.objects.filter(active=True).values_list("key", flat=True))
        self.assertIn("adopted", valid, "the change type vocabulary is seeded before an agent reads it")
        typo = "ammendment"
        self.assertNotIn(typo, valid)

        with stub_api_key(agent_principal(scopes={perms.SCOPE_CHANGES_WRITE})):
            response = self.client.patch(
                f"/api/v1/changes/{change.id}",
                data={"changeType": typo, "summary": "A summary that must not be stored either."},
                content_type="application/json",
                HTTP_X_API_KEY=API_KEY_FOR_TESTS,
            )

        self.assertEqual(response.status_code, 422)
        problem = response.json()
        self.assertEqual(problem["code"], "unknown_key")
        self.assertIn(typo, problem["detail"])
        self.assertEqual(sorted(problem["validKeys"]), valid, "the refusal lists the keys the agent may send")

        change.refresh_from_db()
        self.assertEqual(change.change_type.key, "adopted", "nothing is stored on a refusal")
        self.assertNotIn("must not be stored", change.summary)

    def test_wat_s6(self) -> None:
        """WAT-S6

        Links to affected obligations carry a confidence, and the library and the bank
        decide separately (WAT-04).
        Operations: `replaceChangeObligations`, `acceptCaseObligationLink`,
        `removeCaseObligationLink`.

        The library editor's own confirmation is the held half of this feature and is
        asserted in WAT-S4, whose `@integration` owner is `c5-watch-curation-confirm`:
        until `q-editor-confirm` is answered no route moves
        `change_obligation.confirmed_by`, and the note under WAT-S6 in app.md says so.
        """
        run, plain = self._run_with_a_key()
        banks = self._two_banks()
        officer = factories.member(
            banks.inside, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        other = factories.member(banks.outside, roles=("compliance_officer",)).user
        instrument = library_build.instrument(key="fffs-2017-2", regime=_SECURITIES)
        research = library_build.obligation(
            instrument, key="fffs-2017-2-11-4", titles={"en": "Assess the quality of research paid for"}
        )
        reporting = library_build.obligation(
            instrument, key="fffs-2017-2-12-1", titles={"en": "Report transactions by the next working day"}
        )

        # Given an agent linked a change to two obligations with confidence 0.9 and 0.4.
        # The key is the platform's, so the connection must be out of a bank's zone: the
        # member factories above each left one activated (playbook 14).
        tenancy.clear_tenant()
        registered = self._register(
            plain,
            {
                **_change(),
                "agentRunId": str(run.id),
                "termIds": [str(watch_build.term(_SECURITIES).id)],
                "obligationLinks": [
                    {"obligationId": str(research.id), "confidence": 0.9},
                    {"obligationId": str(reporting.id), "confidence": 0.4},
                ],
            },
        )
        self.assertEqual(registered.status_code, 201, registered.content)
        change_id = registered.json()["id"]
        _drain()

        # Then the change screen shows both with the confidence, as suggestions
        read = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(officer, tenant=banks.inside))
        self.assertEqual(read.status_code, 200, read.content)
        suggested = {link["obligationId"]: link for link in read.json()["obligations"]}
        self.assertEqual(
            {key: (value["confidence"], value["confirmed"]) for key, value in suggested.items()},
            {str(research.id): (0.9, False), str(reporting.id): (0.4, False)},
        )

        # When a compliance officer accepts the first and removes the second on its own case
        accepted = self.client.post(
            f"/api/v1/changes/{change_id}/case/obligation-links",
            data={"obligationId": str(research.id)},
            content_type="application/json",
            **sign_in(officer, tenant=banks.inside),
        )
        self.assertEqual(accepted.status_code, 201, accepted.content)
        removed = self.client.delete(
            f"/api/v1/changes/{change_id}/case/obligation-links/{reporting.id}",
            **sign_in(officer, tenant=banks.inside),
        )
        self.assertEqual(removed.status_code, 200, removed.content)

        # Then both decisions are stored on that bank's case and audited
        with transaction.atomic():
            tenancy.activate(banks.inside.id)
            decisions = {row.obligation_id: row.decision for row in CaseObligationLink.objects.all()}
            self.assertEqual(decisions, {research.id: "accepted", reporting.id: "removed"})
            self.assertEqual(AuditEvent.objects.filter(action="case.obligation_link_decided").count(), 2)

        # And the obligation shows "1 open change"
        counted = self.client.get(
            f"/api/v1/obligations/{research.id}/changes", **sign_in(officer, tenant=banks.inside)
        )
        self.assertEqual(counted.status_code, 200, counted.content)
        self.assertEqual(counted.json()["openCount"], 1)

        # And no library row changed: the second link is still a suggestion for everyone
        with transaction.atomic():
            tenancy.clear_tenant()
            links = {row.obligation_id: watch_build.is_a_suggestion(row) for row in ChangeObligation.objects.all()}
            self.assertEqual(links, {research.id: True, reporting.id: True})
        theirs = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(other, tenant=banks.outside))
        self.assertEqual(
            {link["obligationId"]: link["confirmed"] for link in theirs.json()["obligations"]},
            {str(research.id): False, str(reporting.id): False},
            "another bank still sees both, undecided",
        )
        self.assertEqual(theirs.json()["case"]["obligationDecisions"], [])

    def test_wat_s7(self) -> None:
        """WAT-S7

        The "So what?" is AI-drafted until a person confirms or rewrites it per tenant (WAT-05).
        Operations: `saveSoWhat`, `confirmSoWhat`.

        The draft is the agent's, filed with the change it read and recorded in the AI
        output log from what that agent reported (D-66). Each bank confirms its own copy;
        the library's log row is a platform fact and no bank moves it (ruling I).
        """
        run, plain = self._run_with_a_key()
        banks = self._two_banks()
        officer = factories.member(
            banks.inside, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        other = factories.member(banks.outside, roles=("compliance_officer",)).user

        # Given a change with a drafted "So what?" the run filed with it. The key is the
        # platform's, so the connection must be out of a bank's zone first.
        tenancy.clear_tenant()
        registered = self._register(
            plain,
            {
                **_change(),
                "agentRunId": str(run.id),
                "termIds": [str(watch_build.term(_SECURITIES).id)],
                "soWhat": {
                    "text": _DRAFT,
                    "model": "claude-opus-5",
                    "modelVersion": "2026-05-01",
                    "citations": [{"label": "Finansinspektionen", "url": "https://www.fi.se/"}],
                },
            },
        )
        self.assertEqual(registered.status_code, 201, registered.content)
        change_id = registered.json()["id"]
        _drain()

        # Then an ai_generation row carries model, version and purpose
        with transaction.atomic():
            tenancy.clear_tenant()
            # The draft's own row; the filing's classification is a `scope_suggestion` row beside it.
            logged = AiGeneration.objects.get(subject_id=change_id, purpose="so_what")
            self.assertEqual(
                (logged.purpose, logged.model, logged.model_version, logged.status),
                ("so_what", "claude-opus-5", "2026-05-01", "draft"),
            )
            self.assertTrue(
                logged.model_metadata_reported_by_agent, "the agent reported it; bleqq did not measure it"
            )
            before = list(AiGeneration.objects.values())

        # And each bank's copy is labelled an AI draft
        for bank, person in ((banks.inside, officer), (banks.outside, other)):
            with self.subTest(bank=bank.slug):
                read = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(person, tenant=bank))
                self.assertEqual(read.json()["case"]["soWhatText"], _DRAFT)
                self.assertFalse(read.json()["case"]["soWhatConfirmed"])

        # When the officer rewrites it
        saved = self.client.put(
            f"/api/v1/changes/{change_id}/so-what",
            data={"text": _OUR_WORDS},
            content_type="application/json",
            **sign_in(officer, tenant=banks.inside),
        )
        self.assertEqual(saved.status_code, 200, saved.content)

        # Then this bank's copy is confirmed with the person and the time
        body = saved.json()
        self.assertEqual((body["text"], body["confirmed"], body["isAiDraft"]), (_OUR_WORDS, True, False))
        self.assertEqual(body["confirmedByName"], "Sara Lind")
        self.assertIsNotNone(body["confirmedAt"])

        # And another tenant's copy is still the draft
        theirs = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(other, tenant=banks.outside))
        self.assertEqual(theirs.json()["case"]["soWhatText"], _DRAFT)
        self.assertFalse(theirs.json()["case"]["soWhatConfirmed"])

        # Confirming as it stands works the same way, and neither act moves the library's row
        confirmed = self.client.post(
            f"/api/v1/changes/{change_id}/so-what/confirm",
            data={},
            content_type="application/json",
            **sign_in(other, tenant=banks.outside),
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertEqual(confirmed.json()["text"], _DRAFT, "confirming keeps the model's words")
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(list(AiGeneration.objects.values()), before, "the shared log row is nobody's to move")

    @skip("pending: WAT-S8 (WAT-06, chunk 13)")
    def test_wat_s8(self) -> None:
        """WAT-S8

        A tenant requests a source and private sources stay private (WAT-06).
        """

    def _standards_change(self, run: Any, **overrides: Any) -> dict[str, Any]:
        """A new edition of ISO/IEC 27001 as a sweep files it: the standards body as its
        authority, the AI and ICT regime and the standard's own term, named by its reference
        alone (INV-08)."""
        return {
            "stableKey": "iso-iec-27001-amd-1",
            "title": "ISO/IEC 27001 amendment",
            "changeType": "consultation",
            "authorityCode": "iso-iec",
            "authorityLabel": "ISO/IEC",
            "summary": "An amendment to ISO/IEC 27001 is out as a draft for comment.",
            "sourceLabel": "ISO/IEC",
            "sourceUrl": "https://www.iso.org/",
            "termIds": [str(watch_build.term(_AI_ICT).id), str(watch_build.term(_ISO_27001).id)],
            "agentRunId": str(run.id),
            **overrides,
        }

    def test_wat_s10(self) -> None:
        """WAT-S10

        A new edition of a standard is one change, and only tenants that follow it see it (WAT-02, WAT-07, CAS-01).
        Operations: `createChange`, `listChanges`, `getRoadmap`.

        Case creation reads the same opt-in rule as the feed and the roadmap
        (apps/taxonomy/matching.py), so tenant B's case exists and is marked outside its
        scope rather than missing: CAS-01 opens one case per bank per change.
        """
        run, plain = self._run_with_a_key()
        library_build.authority(key="iso-iec", short_name="ISO/IEC", jurisdiction="intl")
        creation.register()
        today = timezone.localdate()
        transition_ends = today + datetime.timedelta(days=120)

        # Given tenant A follows "ISO/IEC 27001" and tenant B follows no standard
        follower = factories.tenant(slug="follows-iso", name="Example Bank AB")
        other = factories.tenant(slug="follows-none", name="Second Bank A/S")
        for tenant, refs in ((follower, (_AI_ICT, _ISO_27001)), (other, (_AI_ICT,))):
            with transaction.atomic():
                tenancy.activate(tenant.id)
                for ref in refs:
                    FootprintTerm.objects.create(tenant=tenant, term=watch_build.term(ref))
        readers = {tenant: factories.member_user(tenant, roles=("reader",)) for tenant in (follower, other)}
        tenancy.clear_tenant()

        # When an agent registers the change "ISO/IEC 27001 amendment" with the authority
        # "ISO/IEC", the term "ISO/IEC 27001", the regime "AI and ICT", a draft-for-comment
        # timeline entry and a key date labelled "Transition ends"
        draft = today - datetime.timedelta(days=30)
        first = self._register(
            plain,
            self._standards_change(
                run,
                keyDate=transition_ends.isoformat(),
                keyDateLabel="Transition ends",
                events=[{"label": "Draft for comment", "eventDate": draft.isoformat(), "occurred": True, "sortOrder": 1}],
            ),
        )
        self.assertEqual(first.status_code, 201, first.content)

        # And later registers the same stable key with its publication date
        again = self._register(
            plain,
            self._standards_change(
                run,
                changeType="adopted",
                events=[{"label": "Published", "eventDate": today.isoformat(), "occurred": True, "sortOrder": 2}],
            ),
        )
        self.assertEqual(again.status_code, 200, again.content)
        _drain()

        # Then one change exists with both timeline entries
        change = RegulatoryChange.objects.get()
        self.assertEqual(again.json()["id"], str(change.id))
        self.assertEqual(
            [(event.label, event.event_date) for event in change.events.order_by("sort_order")],
            [("Draft for comment", draft), ("Published", today)],
        )
        self.assertEqual((change.key_date, change.key_date_label), (transition_ends, "Transition ends"))

        # And each tenant has exactly one case for it, tenant A's matching its scope and tenant B's not
        self.assertEqual(watch_build.cases_per_tenant(change, (follower, other)), {follower: 1, other: 1})
        matches = {}
        for tenant in (follower, other):
            with transaction.atomic():
                tenancy.activate(tenant.id)
                matches[tenant] = ChangeCase.objects.get(change=change).footprint_match
        self.assertEqual(matches, {follower: True, other: False})

        # And the change and the transition date appear in tenant A's feed and roadmap and
        # in neither of tenant B's
        for tenant, expected in ((follower, True), (other, False)):
            with self.subTest(tenant=tenant.slug):
                headers = sign_in(readers[tenant], tenant=tenant)
                feed = self.client.get("/api/v1/changes", **headers)
                self.assertEqual(feed.status_code, 200, feed.content)
                self.assertIs(str(change.id) in [row["id"] for row in feed.json()["items"]], expected)
                roadmap = self.client.get("/api/v1/roadmap", **headers)
                self.assertEqual(roadmap.status_code, 200, roadmap.content)
                dated = [(item["title"], item["date"]) for item in roadmap.json()["items"]]
                self.assertIs((change.title, transition_ends.isoformat()) in dated, expected, dated)

    def test_wat_s11(self) -> None:
        """WAT-S11

        Every change carries a regime, a standard term needs a standards body, and a publisher's page keeps no snapshot (WAT-01, WAT-03, WAT-07).
        Operations: `createChange`, `createSource`, `recordSourceCheck`.
        """
        # Given an agent key with changes:write
        run, plain = self._run_with_a_key()
        library_build.authority(key="iso-iec", short_name="ISO/IEC", jurisdiction="intl")
        tenancy.clear_tenant()

        # When it registers a change with no regime term
        refused = self._register(plain, {**_change(), "agentRunId": str(run.id), "termIds": []})

        # Then the API answers 422 with code "regime_required" and the valid regime keys
        self.assertEqual(refused.status_code, 422, refused.content)
        problem = refused.json()
        self.assertEqual(problem["code"], "regime_required")
        regimes = sorted(term.key for term in TaxonomyTerm.objects.filter(dimension__key="regime", active=True))
        self.assertEqual(sorted(problem["validKeys"]), regimes, "the refusal lists the regimes the agent may send")
        self.assertEqual(RegulatoryChange.objects.count(), 0, "a refusal stores nothing")

        # When it registers a change carrying a standard's term whose authority is a national supervisor
        # (and, the same refusal, one that names no authority at all)
        for authority in ("fi", None):
            with self.subTest(authority=authority):
                body = self._standards_change(run, authorityCode=authority)
                if authority is None:
                    del body["authorityCode"]
                refused = self._register(plain, body)

                # Then the API answers 422 with code "standard_term_only_on_standards"
                self.assertEqual(refused.status_code, 422, refused.content)
                self.assertEqual(refused.json()["code"], "standard_term_only_on_standards")
                self.assertEqual(RegulatoryChange.objects.count(), 0, "a refusal stores nothing")

        # Given the open web sweep fetches a page on a host listed in the standards publisher setting
        page = "https://www.iso.org/standard/27001"
        self.assertIn("iso.org", settings.STANDARDS_PUBLISHER_HOSTS)
        fetched_at = timezone.now().replace(microsecond=0)
        filed = self._register(
            plain,
            self._standards_change(
                run,
                documents=[{"url": page, "isPrimary": True, "fetchedAt": fetched_at.isoformat(), "contentHash": "sha256:" + "a" * 64}],
            ),
        )
        self.assertEqual(filed.status_code, 201, filed.content)

        # Then the stored source document holds the URL, the date and a content hash and no snapshot
        stored = ChangeDocument.objects.get(url=page)
        self.assertEqual((stored.fetched_at, stored.content_hash), (fetched_at, "sha256:" + "a" * 64))
        columns = {field.name for field in ChangeDocument._meta.get_fields()}
        self.assertFalse(
            columns & {"snapshot", "content", "text", "body", "html"}, "no column could hold the page's text"
        )

        # When a change carrying an opt-in term sends a document with a snapshot
        refused = self._register(
            plain,
            self._standards_change(
                run,
                stableKey="iso-iec-27001-amd-2",
                documents=[{"url": "https://www.iso.org/standard/27001-amd-2", "snapshot": "Clause 5.1 ..."}],
            ),
        )

        # Then the API answers 422 with code "validation_error", because no document has a snapshot field
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "validation_error")
        self.assertFalse(RegulatoryChange.objects.filter(stable_key="iso-iec-27001-amd-2").exists())

        # And a source of kind "Standards body" registered inactive gets no automated check
        person = factories.platform_user(email="library.editor@bleqq.example")
        with stub_session(user_principal(permissions={perms.SOURCES_MANAGE}, subject_id=person.id)):
            registered = self.client.post(
                "/api/v1/sources",
                data={"name": "ISO news", "url": "https://www.iso.org/news.html", "kind": "standards_body"},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}",
            )
        self.assertEqual(registered.status_code, 201, registered.content)
        self.assertFalse(registered.json()["active"])
        checked = self.client.post(
            f"/api/v1/agent-runs/{run.id}/source-checks",
            data={"sourceName": "ISO news", "status": "ok", "itemsFound": 1},
            content_type="application/json",
            HTTP_X_API_KEY=plain,
        )
        self.assertEqual(checked.status_code, 422, checked.content)
        self.assertEqual(checked.json()["code"], "source_inactive")
        self.assertFalse(SourceCheck.objects.exists())

    @skip("pending: WAT-S12 (WAT-01, AUD-03, chunk 5)")
    def test_wat_s12(self) -> None:
        """WAT-S12

        A run re-checks the library records of the sources it checked and proposes the correction (WAT-01, AUD-03).
        """
