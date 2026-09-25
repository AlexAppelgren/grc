"""The watch app's one key resolver and the rows it renders back out (apps/watch/keys.py).

Two things are proved here, and the routes that use them are proved in tests_curation.py:

- **A key the library does not hold never reaches a write.** `resolve_keys()` answers 422
  `unknown_key` carrying the list's valid, active keys, so one refusal teaches an agent the
  whole vocabulary instead of leaving it to guess (AC-WAT2). A retired row is not a valid
  key: an admin retires a value to stop new records using it.
- **What a call answers is the library's half and nothing else.** `change_out()` carries no
  bank's case, no tenant text and no tone; a suggestion is rendered as a suggestion.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.library import testing as library_build
from apps.library.models import Instrument, Obligation, RecordStatus
from apps.shared.errors import ProblemError
from apps.shared.tenancy import library_write
from apps.taxonomy.models import ChangeType
from apps.watch import keys
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange

ORDER = ["en"]


class ResolveKeys(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()

    def test_the_rows_come_back_in_the_order_they_were_sent(self) -> None:
        rows = keys.resolve_keys(keys.FLAG_LIST, ["advice_perimeter", "ai"])
        self.assertEqual([row.key for row in rows], ["advice_perimeter", "ai"])

    def test_an_unknown_key_is_refused_with_the_lists_valid_keys(self) -> None:
        with self.assertRaises(ValidationError) as refused:
            keys.resolve_keys(keys.CHANGE_TYPE_LIST, ["ammendment"])
        self.assertEqual(refused.exception.code, "unknown_key")
        extra = refused.exception.extra  # type: ignore[attr-defined]
        self.assertEqual(extra["vocabulary"], keys.CHANGE_TYPE_LIST)
        self.assertIn("adopted", extra["validKeys"])
        self.assertIn("ammendment", " ".join(refused.exception.messages))

    def test_every_unknown_key_of_one_call_is_named(self) -> None:
        with self.assertRaises(ValidationError) as refused:
            keys.resolve_keys(keys.FLAG_LIST, ["ai", "custody", "tax"])
        message = " ".join(refused.exception.messages)
        self.assertIn("custody", message)
        self.assertIn("tax", message)

    def test_a_retired_row_is_not_a_valid_key(self) -> None:
        """An admin retires a value to stop new records using it (VOC-02), so a retired key
        and a key that never existed answer alike: neither may be stored."""
        # A vocabulary row is behind the proposal door and not the watch door, which the
        # watch door itself refuses to open for (apps/watch/tests_write.py).
        with library_write("test"):
            ChangeType.objects.filter(key="supervision").update(active=False)
        with self.assertRaises(ValidationError) as refused:
            keys.resolve_keys(keys.CHANGE_TYPE_LIST, ["supervision"])
        self.assertEqual(refused.exception.code, "unknown_key")
        self.assertNotIn("supervision", refused.exception.extra["validKeys"])  # type: ignore[attr-defined]


class ResolveTerms(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()

    def test_the_terms_come_back_in_the_order_they_were_sent(self) -> None:
        securities = watch_build.term("regime:securities")
        aml = watch_build.term("regime:aml")
        self.assertEqual(
            [term.id for term in keys.resolve_terms([aml.id, securities.id])],
            [aml.id, securities.id],
        )

    def test_an_id_that_is_not_a_term_is_refused(self) -> None:
        missing = uuid.uuid4()
        with self.assertRaises(ValidationError) as refused:
            keys.resolve_terms([missing])
        self.assertEqual(refused.exception.code, "unknown_key")
        self.assertIn(str(missing), " ".join(refused.exception.messages))


class ObligationsFor(TestCase):
    instrument: Instrument
    obligation: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.instrument = library_build.instrument(key="fffs-2017-2", regime="regime:securities")
        cls.obligation = library_build.obligation(cls.instrument, key="fffs-2017-2-11-4", ref_label="11 kap. 4 §")

    def test_the_obligations_are_read_in_one_query(self) -> None:
        with self.assertNumQueries(1):
            found = keys.obligations_for([self.obligation.id])
        self.assertEqual(list(found), [self.obligation.id])

    def test_an_unknown_obligation_is_refused(self) -> None:
        missing = uuid.uuid4()
        with self.assertRaises(ValidationError) as refused:
            keys.obligations_for([self.obligation.id, missing])
        self.assertEqual(refused.exception.code, "unknown_key")
        self.assertIn(str(missing), " ".join(refused.exception.messages))

    def test_a_retired_obligation_is_refused(self) -> None:
        """A link to a retired obligation is a link nobody can follow (INV-03)."""
        with library_write("test"):
            Obligation.objects.filter(pk=self.obligation.id).update(status=RecordStatus.RETIRED.value)
        with self.assertRaises(ValidationError) as refused:
            keys.obligations_for([self.obligation.id])
        self.assertEqual(refused.exception.code, "unknown_key")


class ChangeLookups(TestCase):
    change: RegulatoryChange

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.change = watch_build.change_with_timeline()

    def test_a_change_that_is_not_there_is_404_and_never_403(self) -> None:
        with self.assertRaises(ProblemError) as refused:
            keys.change_for_write(uuid.uuid4())
        self.assertEqual(refused.exception.status, 404)
        self.assertEqual(refused.exception.code, "not_found")

    def test_an_entry_of_another_change_is_404(self) -> None:
        other = watch_build.change()
        entry = watch_build.event(other)
        with self.assertRaises(ProblemError) as refused:
            keys.event_for_write(self.change, entry.id)
        self.assertEqual(refused.exception.status, 404)

    def test_a_superseding_change_that_is_not_there_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as refused:
            keys.change_named(uuid.uuid4())
        self.assertEqual(refused.exception.code, "unknown_key")


class ChangeOut(TestCase):
    instrument: Instrument
    obligation: Obligation
    change: RegulatoryChange

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.instrument = library_build.instrument(key="fffs-2017-2", regime="regime:securities")
        cls.obligation = library_build.obligation(
            cls.instrument,
            key="fffs-2017-2-11-4",
            titles={"en": "Assess the quality of investment research paid for"},
            ref_label="11 kap. 4 §",
        )
        cls.change = watch_build.change_with_timeline()
        watch_build.document(cls.change, url="https://www.fi.se/en/second-sighting/", is_primary=False, is_duplicate=True)
        watch_build.obligation_link(cls.change, cls.obligation)

    def test_the_library_half_of_a_change_reads_back_whole(self) -> None:
        row = keys.change_out(self.change, ORDER)
        self.assertEqual(row.stable_key, self.change.stable_key)
        self.assertEqual(row.change_type.key, "adopted")
        self.assertEqual([flag.key for flag in row.flags], ["advice_perimeter"])
        self.assertEqual([term.key for term in row.terms], ["securities"])
        self.assertEqual([event.label for event in row.events], ["Consultation closed", "In force"])
        self.assertEqual(row.duplicate_count, 1, "a second sighting of the same reform is a duplicate page (AC-WAT1)")
        self.assertIsNotNone(row.suggested_urgency)

    def test_a_link_carries_the_agents_confidence_and_reads_unconfirmed(self) -> None:
        link = keys.change_out(self.change, ORDER).obligations[0]
        self.assertEqual(link.title, "Assess the quality of investment research paid for")
        self.assertEqual(link.instrument_short_name, self.instrument.short_name)
        self.assertEqual(link.ref_label, "11 kap. 4 §")
        self.assertEqual(link.origin, "agent")
        self.assertEqual(link.confidence, 0.82)
        self.assertFalse(link.confirmed, "nobody has confirmed it, and false never means 'not related'")

    def test_an_untranslated_obligation_still_renders(self) -> None:
        """A link has to render before anyone has written a title in the reader's language
        (INV-05), so the stable key stands in rather than an empty row."""
        bare = library_build.obligation(self.instrument, key="fffs-2017-2-11-5", titles={})
        watch_build.obligation_link(self.change, bare)
        titles = {link.title for link in keys.links_out(self.change, ORDER)}
        self.assertIn("fffs-2017-2-11-5", titles)

    def test_no_tone_and_no_bank_reaches_the_response(self) -> None:
        """A pill's tone follows its slot or its row's kind and is nobody's to send
        (NFR-03), and a change is a library row: no case, no tenant, no judgement."""
        body = keys.change_out(self.change, ORDER).model_dump(by_alias=True)
        text = str(body).lower()
        for forbidden in ("tone", "colour", "tenant", "case"):
            self.assertNotIn(forbidden, text)
