"""What changed in the shared library since a bank last looked (chunk 4, PRO-03, INV-04,
FP-03).

The rules this pins: the list starts at the reader's own bookmark and falls back to the
window setting; a change reaches a bank only if the duty it touched is inside that bank's
footprint, unless the reader asks for the rest; a change to a shared list reaches every
bank, under the list row's own label and never under the wording of the request that
carried it; days are the bank's own days; and the cost does not grow with the number of
changes on the page.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from zoneinfo import ZoneInfo

from apps.identity.models import Membership
from apps.library.models import (
    Instrument,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import logic
from apps.proposals.models import Proposal
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy import footprint_logic
from apps.taxonomy.models import DutyType, Flag, InstrumentLevel, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

V1 = "/api/v1"
SOURCE = "https://www.fi.se/"
# The whole answer costs this much, re-measured 2026-09-22 after chunk3-rest-T13 (an
# obligation's scope now inherits through its instrument's own, `library.reading.
# instrument_scopes()`, so the single footprint rule agrees for instruments too): the
# scenario client's audit count (1), the request's savepoint pair (2), the auth layer for a
# tenant session (6), the reader's own locale and their bank's language (2), their
# membership for the bookmark (1), how many changes there are and the page (2), the records
# the page names (2), the versions those changes wrote (1), and the footprint verdict,
# which is `obligation_scopes()`'s own five queries (its own terms, its instrument id, and
# `instrument_scopes()`'s pair and term lookups), the bank's footprint (1), the dimensions
# that restrict it (1) and the dimensions and terms a screen names them by (3).
UPDATES_QUERIES = 1 + 2 + 6 + 2 + 1 + 2 + 2 + 1 + 9


class LibraryUpdates(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.reader = factories.member(self.tenant, roles=("reader",)).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.instrument = self._instrument()
        # The bank advises retail clients and does not execute orders, so a duty whose only
        # service is execution is outside its footprint (FP-01).
        self._footprint("service_type:advice", "client_category:retail")

    # --- fixtures ----------------------------------------------------------------------
    def _instrument(self) -> Instrument:
        with library_write("test"):
            return Instrument.objects.create(
                stable_key="fffs-2017-2",
                short_name="FFFS 2017:2",
                official_ref="FFFS 2017:2",
                source_url=SOURCE,
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                created_origin="user",
            )

    def _footprint(self, *refs: str) -> None:
        self.activate(self.tenant)
        footprint_logic.seed_terms(
            tenant=self.tenant,
            actor=Actor.system("test"),
            terms=[TaxonomyTerm.objects.get(dimension__key=ref.split(":")[0], key=ref.split(":")[1]) for ref in refs],
        )

    def _obligation(self, stable_key: str, *terms: str) -> Obligation:
        with library_write("test"):
            obligation = Obligation.objects.create(
                stable_key=stable_key,
                instrument=self.instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.get(key="conduct"),
                created_origin="user",
                source_url=SOURCE,
                source_label="FFFS 2017:2, 9 kap. 6 §",
            )
            ObligationTitle.objects.create(obligation=obligation, language_id="en", text=f"Duty {stable_key}", is_original=True)
            version = ObligationVersion.objects.create(obligation=obligation, version_number=1, effective_from=datetime.date(2024, 1, 1))
            ObligationSummary.objects.create(version=version, language_id="sv", text="Institutet bedömer kunden.", is_original=True)
            for ref in terms:
                dimension, key = ref.split(":")
                ObligationTerm.objects.create(obligation=obligation, term=TaxonomyTerm.objects.get(dimension__key=dimension, key=key))
        return obligation

    def _apply_version(self, obligation: Obligation) -> Proposal:
        """An agent proposes a new version and a library editor approves it, which is the
        only way a change reaches the library."""
        tenancy.clear_tenant()
        proposal, _ = logic.create(
            kind="new_obligation_version",
            title=f"Version 2 of {obligation.stable_key}",
            payload={
                "summaries": {"sv": "Institutet bedömer kunden varje år."},
                "originalLanguage": "sv",
                "isMachine": True,
                "effectiveFrom": "2026-10-01",
                "effectiveFromPrecision": "quarter",
            },
            proposer=logic.Proposer(actor=factories.user_actor(), agent_run_id=None),
            target_type="obligation",
            target_id=obligation.id,
            field_sources={"summaries.sv": SOURCE, "effectiveFrom": SOURCE},
            source_label="Finansinspektionen",
            source_url=SOURCE,
        )
        return self._approve(proposal)

    def _approve(self, proposal: Proposal) -> Proposal:
        tenancy.clear_tenant()
        return logic.approve(
            proposal=proposal,
            reviewer=self.editor,
            actor=Actor(kind=ActorType.USER, id=self.editor.id, label=self.editor.name),
            note="",
            step_up_assertion_id=uuid.uuid4(),
        )

    def _read(self, user: Any, tenant: Any, query: str = "") -> dict[str, Any]:
        answer = self.client.get(f"{V1}/library-updates{query}", **sign_in(user, tenant=tenant))
        self.assertEqual(answer.status_code, 200, answer.content)
        body: dict[str, Any] = answer.json()
        return body

    def _items(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for day in body["days"] for item in day["items"]]

    # --- what a bank sees ---------------------------------------------------------------
    def test_a_reader_sees_the_new_version_titled_by_the_library_record(self) -> None:
        obligation = self._obligation("obl-advice-suitability", "service_type:advice")
        self._apply_version(obligation)

        body = self._read(self.reader, self.tenant)
        self.assertEqual(body["total"], 1)
        item = self._items(body)[0]
        self.assertEqual(item["kind"], "new_obligation_version")
        self.assertEqual(item["target"]["title"], "Duty obl-advice-suitability", "the record's own title, never the proposal's")
        self.assertEqual(item["target"]["instrumentShortName"], "FFFS 2017:2")
        self.assertEqual(item["versionNumber"], 2)
        self.assertEqual(item["effectiveFrom"], {"date": "2026-10-01", "precision": "quarter"})
        self.assertTrue(item["inFootprint"])
        self.assertEqual(item["outsideReason"], [])
        self.assertNotIn("proposedBy", item, "who asked for a change is not a bank's business")
        # The day is the bank's own day, and the list starts at the window when nobody has
        # marked the library as seen yet.
        applied = Proposal.objects.get(pk=item["id"]).applied_at
        assert applied is not None
        self.assertEqual(body["days"][0]["date"], timezone.localdate(applied, timezone=ZoneInfo(self.tenant.timezone)).isoformat())
        self.assertLess(body["since"], applied.isoformat())

    def test_a_duty_outside_the_footprint_is_hidden_until_the_reader_asks_for_it(self) -> None:
        """FP-03: the same rule the inventory applies. Asking for the rest says which facet
        would have hidden each one."""
        outside = self._obligation("obl-execution-only", "service_type:execution_only")
        self._apply_version(outside)

        hidden = self._read(self.reader, self.tenant)
        self.assertEqual((hidden["total"], hidden["days"]), (0, []), "it is not counted either, not only unprinted")

        shown = self._read(self.reader, self.tenant, "?outsideFootprint=true")
        item = self._items(shown)[0]
        self.assertFalse(item["inFootprint"])
        self.assertEqual([reason["dimension"]["key"] for reason in item["outsideReason"]], ["service_type"])
        self.assertEqual([term["key"] for term in item["outsideReason"][0]["terms"]], ["execution_only"])

    def test_the_list_starts_at_the_readers_own_bookmark(self) -> None:
        obligation = self._obligation("obl-advice-suitability", "service_type:advice")
        self._apply_version(obligation)
        self.activate(self.tenant)
        membership = Membership.objects.get(tenant=self.tenant, user=self.reader)
        membership.last_visit_at = timezone.now()
        membership.save(update_fields=["last_visit_at"])

        body = self._read(self.reader, self.tenant)
        self.assertEqual(body["total"], 0, "everything applied before they marked it as seen is behind them")
        self.assertEqual(body["since"][:10], timezone.now().date().isoformat())

    @override_settings(LIBRARY_UPDATES_DEFAULT_DAYS=1)
    def test_a_reader_who_never_marked_it_as_seen_reads_the_window(self) -> None:
        obligation = self._obligation("obl-advice-suitability", "service_type:advice")
        proposal = self._apply_version(obligation)
        Proposal.objects.filter(pk=proposal.id).update(applied_at=timezone.now() - datetime.timedelta(days=3))

        self.assertEqual(self._read(self.reader, self.tenant)["total"], 0, "older than the window the setting allows")
        with override_settings(LIBRARY_UPDATES_DEFAULT_DAYS=30):
            self.assertEqual(self._read(self.reader, self.tenant)["total"], 1)

    def test_a_vocabulary_change_one_bank_asked_for_reaches_another_under_the_rows_own_label(self) -> None:
        """PRO-03: tenant A's wording is its own. Tenant B is told which row of which shared
        list changed, labelled as the list labels it, and never told who asked or how they
        described it."""
        officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        made = self.client.post(
            f"{V1}/vocab/flag",
            data={"labels": {"en": "Client money", "sv": "Kundmedel"}},
            content_type="application/json",
            **sign_in(officer, tenant=self.tenant),
        )
        self.assertEqual(made.status_code, 202, made.content)
        self.activate(self.tenant)
        proposal = Proposal.objects.get(pk=made.json()["proposal"]["id"])
        self._approve(proposal)
        self.assertTrue(Flag.objects.filter(key="client_money").exists())

        other = factories.tenant(slug="second-bank")
        reader_there = factories.member(other, roles=("reader",)).user
        body = self._read(reader_there, other)
        item = self._items(body)[0]
        self.assertEqual(item["vocabularyList"], "flag")
        self.assertEqual(item["vocabulary"], {"key": "client_money", "kind": None, "label": "Client money"})
        self.assertIsNone(item["target"])
        self.assertTrue(item["inFootprint"], "a shared list belongs to every bank and to no footprint")
        self.assertNotIn(proposal.title, repr(item), "the request's own wording never reaches another bank")

    def test_the_kind_filter_narrows_the_list(self) -> None:
        self._apply_version(self._obligation("obl-advice-suitability", "service_type:advice"))
        self.assertEqual(self._read(self.reader, self.tenant, "?kind=new_obligation_version")["total"], 1)
        self.assertEqual(self._read(self.reader, self.tenant, "?kind=vocabulary_create")["total"], 0)

    def test_the_list_is_a_persons_and_needs_the_library_read(self) -> None:
        # An agent's key holds no bookmark and reads no screen, so the route takes a session
        # only: a key is not refused for want of a scope, it is not signed in at all.
        key = factories.api_key(self.tenant, scopes=("library:read",))
        refused = self.client.get(f"{V1}/library-updates", HTTP_X_API_KEY=key.plain_key)
        self.assertEqual(refused.status_code, 401, refused.content)
        # A platform session is in no organisation, so there is no footprint to read against.
        self.assertEqual(self.client.get(f"{V1}/library-updates", **sign_in(self.editor)).status_code, 403)

    def test_the_list_costs_the_same_whatever_it_holds(self) -> None:
        self._apply_version(self._obligation("obl-advice-suitability", "service_type:advice"))
        reader = sign_in(self.reader, tenant=self.tenant)
        with CaptureQueriesContext(connection) as one:
            self.client.get(f"{V1}/library-updates", **reader)
        for number in (2, 3):
            self._apply_version(self._obligation(f"obl-another-{number}", "service_type:advice"))
        with CaptureQueriesContext(connection) as three:
            answer = self.client.get(f"{V1}/library-updates", **reader)
        self.assertEqual(answer.json()["total"], 3)
        self.assertEqual(len(three.captured_queries), len(one.captured_queries))
        self.assertEqual(len(one.captured_queries), UPDATES_QUERIES)

    def test_a_page_holds_the_limit_and_the_total_counts_the_rest(self) -> None:
        for number in (1, 2):
            self._apply_version(self._obligation(f"obl-advice-{number}", "service_type:advice"))
        page = self._read(self.reader, self.tenant, "?limit=1")
        self.assertEqual((len(self._items(page)), page["total"]), (1, 2))
        refused = self.client.get(f"{V1}/library-updates?limit=101", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(refused.status_code, 422, refused.content)
