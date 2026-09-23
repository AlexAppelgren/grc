"""Guard: the database refuses a library-zone write that never entered a door (hardening
H16, ADR 0058, PRO-01, NFR-01, AC-PRO1).

The Python fence (`library_write()`, its AST guard and the watch and index doors) decides
who may write a library row. It stops at Python: an ORM call that never reaches
`LibraryModel.save()` or the fenced queryset — the base `QuerySet.update()`, a collector's
fast delete, raw SQL — and a bank session holding the app role could still change a shared
record. Shared 0008 adds a second layer in the database itself. Every library-zone table
carries one statement-level trigger that refuses INSERT, UPDATE, DELETE and TRUNCATE unless
the transaction-local setting the doors set names a door that table accepts: the watch door
the seven watch tables only (D-64), the index door `search_chunk` only (D-65), the
re-verification stamp `obligation` and `verification` only, a reference seed alone the
library app's reference rows (`language`, `jurisdiction`, `jurisdiction_label`), and an
approved proposal or a reference seed every other library table. The schema owner passes by
`session_user`, so a migration, the E2E seed and this runner's own `default` connection are
let through.

What is proven here:

- **The census.** Every concrete `LibraryModel`'s table, plus `search_chunk` and the three
  reference tables, read from the app registry and not from the migration's list, carries
  the trigger with exactly the doors above, and no other table carries it. A new library
  table without it fails here, and so does a new shared row (one with no tenant) in a
  library-zone app that is neither a `LibraryModel` nor named here.
- **Refusal as the app role in a bank's zone.** On the `app` alias (cw_app, no ownership),
  with a bank activated, an INSERT, UPDATE and DELETE on every library-zone table is refused
  outside a door, each door opens exactly the tables it names, and the schema owner passes.
  The statements touch no row: a statement-level trigger fires before any row is read, so a
  write that would change nothing is still a write the database refuses.
- **The doors still write.** With the runner's `default` alias pointed at the cw_app
  connection, the same writes through `library_write()`, `watch_write()`, `index_write()`
  (by way of a real rebuild), the reference seeds and the re-verification stamp succeed,
  while an ORM write that slips past the Python fence is refused by the database.
- **Every real writer, as the app role.** The rest of the suite runs as the schema owner,
  whom the trigger lets through, so a writer that names the wrong door — a vocabulary merge
  that moves a watch row inside the proposal door, say — would pass it and fail only in
  E2E. Here every proposal kind is filed and approved through `proposals.logic` as a
  console request does it, every list and term kind again as one agent files it and an
  agent of another definition approves it (D-79, lifted 2026-09-23), and every watch step writes through its own entry point, all on
  the cw_app connection. Two censuses keep that whole: every `ProposalKind` must be
  approved here, and every module allowed to open the watch door must be exercised here,
  so a new kind or a new watch step fails this guard until it is proven as the app role.
- **A door lasts only as long as its transaction.** A door set in autocommit is gone by the
  next statement, which is why every door opens a transaction (a savepoint inside one).

What it does not stop, stated in ADR 0058: code running as cw_app that sets the setting
itself. The compliance lint's `library-door` rule and the AST pins in
tests_library_fence.py keep the setting's name and each door's value in their own modules.

Proven to fail 2026-09-23 against the tree before shared 0008: the census named every
library table as missing its trigger, and every refusal assertion below failed with the
write accepted.

Proven to fail 2026-09-24, each breach then reverted: a `change_term` repoint planted in
`apply._vocabulary_merge` inside the proposal door (green in apps/proposals/tests_apply.py,
which runs as the owner; red here, "UPDATE on change_term refused: the door open is
proposal"); `watch_write()` naming the proposal door (both real-writer tests red on
`regulatory_change`); `seed_jurisdictions()` without its door (red on `jurisdiction`); the
reference tables' triggers left out of shared 0008 (the census and nine refusals red); and
`jurisdiction_label` left out of REFERENCE_TABLES (both censuses red).
"""

from __future__ import annotations

import datetime
import typing
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest import mock

from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections, models, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.agents import testing as agents_testing
from apps.governance.models import AiGeneration
from apps.library import testing as library_testing
from apps.library.models import (
    InstrumentTitle,
    Jurisdiction,
    JurisdictionLabel,
    Language,
    Obligation,
    ObligationTitle,
    ObligationVersion,
    Provision,
    Verification,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import apply, logic as proposals
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.search import indexing
from apps.search.models import SearchChunk
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.migration_helpers import LIBRARY_DOOR_FUNCTION, LIBRARY_DOOR_SETTING
from apps.shared.schemas import AgentDecision
from apps.shared.tenancy import LibraryDoor, LibraryModel, library_door, library_write
from apps.shared.testing import production_models, user_principal
from apps.shared.tests_library_fence import WATCH_WRITE_ALLOWLIST
from apps.taxonomy.models import Flag, SourceKind, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.watch import curation, registration, so_what_draft, sources, testing as watch_testing
from apps.watch.models import ChangeObligation, ChangeTerm, RegulatoryChange, Source
from apps.watch.schemas import WatchChangeEventInput, WatchChangeInput, WatchChangePatch, WatchSoWhatInput, WatchSourceInput
from apps.watch.write import WATCH_TABLES, watch_write

APP = "app"
EVERY_DOOR: tuple[str, ...] = ("proposal", "reverification", "seed", "watch", "index")
# Stated here and not imported from the migration helpers, so a helper that quietly widens
# a door fails this guard instead of moving it.
INVENTORY_DOORS = ("proposal", "seed")
STAMPED_DOORS = ("proposal", "reverification", "seed")
WATCH_DOORS = ("watch",)
INDEX_DOORS = ("index",)
REFERENCE_DOORS = ("seed",)
STAMPED_TABLES = frozenset({Obligation._meta.db_table, Verification._meta.db_table})
# The library app's reference rows: shared by every bank, written by no proposal (the
# jurisdiction list is not proposable), and not `LibraryModel`s, so the Python fence never
# sees them and the database is the only thing holding them.
REFERENCE_TABLES = frozenset(model._meta.db_table for model in (Language, Jurisdiction, JurisdictionLabel))
# The apps whose shared rows are library-zone rows. A model of theirs with no `tenant`
# column is either a `LibraryModel`, `search_chunk` or a reference table above.
LIBRARY_ZONE_APPS = frozenset({"library", "taxonomy", "watch", "search", "agents"})

# What a console request passes as the reader's language order.
ORDER = ["en"]
SOURCE_URL = "https://www.fi.se/"
SO_WHAT = {
    "text": "Teams that pay for external research should confirm that documented criteria exist.",
    "model": "agent pipeline 0.4",
    "modelVersion": "2026-05-01",
    "citations": [{"label": "Finansinspektionen", "url": SOURCE_URL}],
}

# pg_trigger.tgtype bits (PostgreSQL 16, include/catalog/pg_trigger.h): ROW 1, BEFORE 2,
# INSERT 4, DELETE 8, UPDATE 16, TRUNCATE 32. A statement-level BEFORE trigger on all four.
BEFORE_EVERY_WRITE_PER_STATEMENT = 2 | 4 | 8 | 16 | 32

WRITES = {
    # Zero-row statements: the trigger is per statement, so it fires before any row is
    # read, and a door that lets the statement through changes nothing. Only `id` is named
    # on the insert, because `search_chunk.tsv` is a generated column.
    "INSERT": 'INSERT INTO "{table}" (id) SELECT id FROM "{table}" WHERE false',
    "UPDATE": 'UPDATE "{table}" SET id = id WHERE false',
    "DELETE": 'DELETE FROM "{table}" WHERE false',
}


def library_zone_tables() -> dict[str, tuple[str, ...]]:
    """Every library-zone table and the doors it accepts, from the app registry."""
    tables: dict[str, tuple[str, ...]] = {}
    for model in production_models():
        if not issubclass(model, LibraryModel) or model._meta.abstract:
            continue
        table = model._meta.db_table
        if table in WATCH_TABLES:
            tables[table] = WATCH_DOORS
        elif table in STAMPED_TABLES:
            tables[table] = STAMPED_DOORS
        else:
            tables[table] = INVENTORY_DOORS
    tables[SearchChunk._meta.db_table] = INDEX_DOORS
    tables.update(dict.fromkeys(REFERENCE_TABLES, REFERENCE_DOORS))
    return tables


def open_door(using: str = DEFAULT_DB_ALIAS) -> str:
    """The door the database sees on `using`: empty outside every door."""
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT coalesce(current_setting(%s, true), '')", [LIBRARY_DOOR_SETTING])
        row = cursor.fetchone()
    return row[0] if row else ""


@contextmanager
def as_the_app_role() -> Iterator[None]:
    """Point the runner's `default` alias at the cw_app connection for the block.

    Every door writes through `default`, which in production is cw_app and in this runner
    is the schema owner (config/test_settings.py), whom the trigger lets through for
    migrations. Swapping the connection object is what lets the real doors run against the
    trigger unchanged, rather than a copy of them written for the test."""
    owner = connections[DEFAULT_DB_ALIAS]
    connections[DEFAULT_DB_ALIAS] = connections[APP]
    try:
        yield
    finally:
        connections[DEFAULT_DB_ALIAS] = owner


class EveryLibraryTableCarriesTheDoorTrigger(TestCase):
    """The census, read from `pg_trigger` on the real database."""

    def _triggers(self) -> dict[str, tuple[int, str, tuple[str, ...]]]:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relname, t.tgtype, t.tgenabled, t.tgargs, t.tgnargs
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_proc p ON p.oid = t.tgfoid
                WHERE p.proname = %s AND NOT t.tgisinternal
                """,
                [LIBRARY_DOOR_FUNCTION],
            )
            rows = cursor.fetchall()
        found: dict[str, tuple[int, str, tuple[str, ...]]] = {}
        for table, kind, enabled, raw_args, count in rows:
            self.assertNotIn(table, found, f"{table} carries the library door trigger twice")
            args = tuple(part.decode() for part in bytes(raw_args).split(b"\x00")[:count])
            found[table] = (kind, enabled, args)
        return found

    def test_every_library_zone_table_carries_the_trigger_with_the_doors_it_accepts(self) -> None:
        expected = library_zone_tables()
        found = self._triggers()
        self.assertEqual(
            sorted(set(expected) - set(found)),
            [],
            "library-zone tables without the door trigger; attach it in the migration that creates "
            "the table with library_door_trigger_operations() (apps/shared/migration_helpers.py, ADR 0058)",
        )
        self.assertEqual(sorted(set(found) - set(expected)), [], "the door trigger sits on a table outside the library zone")
        for table, doors in expected.items():
            kind, enabled, args = found[table]
            with self.subTest(table=table):
                self.assertEqual(args, doors, f"{table} accepts the wrong doors")
                self.assertEqual(kind, BEFORE_EVERY_WRITE_PER_STATEMENT, f"{table}: not BEFORE INSERT, UPDATE, DELETE and TRUNCATE per statement")
                self.assertEqual(enabled, "O", f"{table}: the trigger is not enabled")

    def test_the_census_sees_the_zone_it_is_meant_to(self) -> None:
        tables = library_zone_tables()
        self.assertLessEqual({"authority", "instrument", "obligation", "obligation_version", "taxonomy_term", "agent"}, set(tables))
        self.assertLessEqual(WATCH_TABLES, set(tables))
        self.assertEqual(tables["search_chunk"], INDEX_DOORS)
        self.assertEqual(tables["verification"], STAMPED_DOORS)
        self.assertEqual(tables["regulatory_change"], WATCH_DOORS)
        self.assertEqual(tables["authority"], INVENTORY_DOORS)
        self.assertEqual(REFERENCE_TABLES, {"language", "jurisdiction", "jurisdiction_label"})
        self.assertEqual(tables["jurisdiction"], REFERENCE_DOORS)

    def test_every_shared_row_of_a_library_zone_app_is_in_the_census(self) -> None:
        # A model with no tenant column in an app that holds library rows is a row every bank
        # shares. The Python fence sees only `LibraryModel`s, so one that is not has nothing
        # in front of it unless the trigger is: a new one fails here until it is a
        # LibraryModel, or is named in REFERENCE_TABLES and given the trigger.
        shared = {
            model._meta.db_table
            for model in production_models()
            if model._meta.app_label in LIBRARY_ZONE_APPS
            and not model._meta.abstract
            and not any(field.name == "tenant" for field in model._meta.concrete_fields)
        }
        self.assertEqual(
            sorted(shared - set(library_zone_tables())),
            [],
            "shared rows of a library-zone app outside the door census; make the model a LibraryModel "
            "or name it in REFERENCE_TABLES, and attach the trigger (ADR 0058)",
        )

    def test_the_doors_the_code_names_are_the_doors_the_database_knows(self) -> None:
        in_the_database = {door for doors in library_zone_tables().values() for door in doors}
        self.assertEqual(set(typing.get_args(LibraryDoor)), in_the_database)
        self.assertEqual(set(EVERY_DOOR), in_the_database)

    def test_the_owner_is_recognised_by_session_user_and_the_function_runs_as_its_caller(self) -> None:
        # session_user, never current_user, which a SECURITY DEFINER function or a cascade
        # changes (shared 0005, the H-B review).
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT prosrc, prosecdef FROM pg_proc WHERE proname = %s", [LIBRARY_DOOR_FUNCTION])
            source, security_definer = cursor.fetchone()
        self.assertIn("session_user", source)
        self.assertNotIn("current_user", source)
        self.assertFalse(security_definer)


class TheDatabaseRefusesAWriteOutsideADoor(TransactionTestCase):
    """Raw SQL on the `app` alias, as cw_app, inside a bank's zone."""

    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        self.bank = factories.tenant(slug="door-guard-bank")

    def _refusal(self, sql: str, door: str | None) -> str | None:
        """Run `sql` as cw_app in the bank's zone, inside `door` when one is given, and
        return the database's refusal, or None when the statement went through."""
        with transaction.atomic(using=APP):
            tenancy.activate(self.bank.id, using=APP)
            try:
                with transaction.atomic(using=APP), connections[APP].cursor() as cursor:
                    if door is None:
                        cursor.execute(sql)
                    else:
                        with library_door(typing.cast(LibraryDoor, door), using=APP):
                            cursor.execute(sql)
            except DatabaseError as refused:
                return str(refused)
        return None

    def test_every_write_outside_a_door_is_refused_on_every_library_table(self) -> None:
        for table in sorted(library_zone_tables()):
            for verb, template in WRITES.items():
                with self.subTest(table=table, verb=verb):
                    refusal = self._refusal(template.format(table=table), door=None)
                    self.assertIsNotNone(refusal, f"{verb} on {table} went through outside a door")
                    assert refusal is not None
                    self.assertIn(f"{verb} on {table} refused", refusal)
                    self.assertIn("the door open is none", refusal)

    def test_each_door_opens_the_tables_it_names_and_no_other(self) -> None:
        for table, doors in sorted(library_zone_tables().items()):
            for door in EVERY_DOOR:
                with self.subTest(table=table, door=door):
                    refusal = self._refusal(WRITES["UPDATE"].format(table=table), door=door)
                    if door in doors:
                        self.assertIsNone(refusal, f"the {door} door should open {table}")
                    else:
                        self.assertIsNotNone(refusal, f"the {door} door opened {table}")
                        assert refusal is not None
                        self.assertIn(f"the door open is {door}", refusal)

    def test_the_schema_owner_passes_for_migrations(self) -> None:
        for table in sorted(library_zone_tables()):
            with self.subTest(table=table), transaction.atomic(), connections[DEFAULT_DB_ALIAS].cursor() as cursor:
                for template in WRITES.values():
                    cursor.execute(template.format(table=table))

    def test_the_setting_in_any_letter_case_is_the_same_door_and_opens_nothing_unnamed(self) -> None:
        # PostgreSQL folds a setting name, so the doors' own spelling and an upper-case one
        # are one setting; the value is compared exactly, so a door must be named as the
        # trigger names it.
        for spelling, value, opens in (
            ("CW.LIBRARY_DOOR", "proposal", True),
            ("cw.library_door", "Proposal", False),
            ("cw.library_door", "proposal, watch", False),
            ("cw.library_door", "", False),
        ):
            with self.subTest(spelling=spelling, value=value), transaction.atomic(using=APP):
                tenancy.activate(self.bank.id, using=APP)
                try:
                    with transaction.atomic(using=APP), connections[APP].cursor() as cursor:
                        cursor.execute("SELECT set_config(%s, %s, true)", [spelling, value])
                        cursor.execute(WRITES["UPDATE"].format(table="obligation"))
                    went_through = True
                except DatabaseError:
                    went_through = False
                self.assertEqual(went_through, opens)

    def test_a_door_set_outside_a_transaction_is_gone_by_the_next_statement(self) -> None:
        # Why every door opens a transaction: set_config(..., true) outside one lasts for
        # its own statement only, so the write after it arrives with no door at all.
        app = connections[APP]
        self.assertFalse(app.in_atomic_block)
        with app.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, true)", [LIBRARY_DOOR_SETTING, "seed"])
            with self.assertRaises(DatabaseError) as refused:
                cursor.execute(WRITES["UPDATE"].format(table="authority"))
        self.assertIn("the door open is none", str(refused.exception))


class TheDoorsWriteAsTheAppRole(TransactionTestCase):
    """The real doors against the trigger, as cw_app: what they write goes through, and
    what slips past the Python fence does not."""

    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
            seed_authorities()
        self.bank = factories.tenant(slug="door-writer-bank")
        self.checker = factories.user()
        self.instrument = library_testing.instrument(key="door-guard-act", regime="regime:securities")
        self.obligation = library_testing.obligation(self.instrument, key="door-guard-act/1")

    def test_a_write_that_slips_past_the_python_fence_is_refused_by_the_database(self) -> None:
        with as_the_app_role(), transaction.atomic():
            tenancy.activate(self.bank.id)
            # The base QuerySet methods, not the fenced LibraryQuerySet ones: the Python
            # fence never sees these, which is the gap this layer closes.
            with self.assertRaises(DatabaseError) as refused, transaction.atomic():
                models.QuerySet.update(Obligation.objects.filter(pk=self.obligation.pk), product_scope="a bank's rewrite")
            self.assertIn("UPDATE on obligation refused", str(refused.exception))
            with self.assertRaises(DatabaseError) as refused, transaction.atomic():
                models.QuerySet.delete(ObligationTitle.objects.filter(obligation=self.obligation))
            self.assertIn("DELETE on obligation_title refused: the door open is none", str(refused.exception))
            with self.assertRaises(DatabaseError) as refused, transaction.atomic(), connections[DEFAULT_DB_ALIAS].cursor() as cursor:
                cursor.execute("UPDATE authority SET name = name")
            self.assertIn("UPDATE on authority refused: the door open is none", str(refused.exception))
            # A reference row, which no LibraryModel fence sees at all.
            with self.assertRaises(DatabaseError) as refused, transaction.atomic():
                models.QuerySet.update(Jurisdiction.objects.filter(key="no"), active=False)
            self.assertIn("UPDATE on jurisdiction refused: the door open is none", str(refused.exception))
            # Inside the index door, which opens search_chunk and nothing else.
            with self.assertRaises(DatabaseError) as refused, transaction.atomic(), indexing.index_write("a rebuild"):
                models.QuerySet.update(Obligation.objects.filter(pk=self.obligation.pk), product_scope="a rebuild's rewrite")
            self.assertIn("the door open is index", str(refused.exception))
        self.assertEqual(Obligation.objects.get(pk=self.obligation.pk).product_scope, "")
        self.assertTrue(ObligationTitle.objects.filter(obligation=self.obligation).exists())

    def test_every_door_still_writes_its_own_tables(self) -> None:
        with as_the_app_role():
            # A reference seed as a deploy runs it, with no transaction open around it: the
            # door opens its own, because the setting lasts only as long as one.
            self.assertFalse(connections[DEFAULT_DB_ALIAS].in_atomic_block)
            provision = library_testing.provision(self.instrument, key="door-guard-act/9")
            # The reference seeds a deploy re-runs: every row exists, so each is an UPDATE of a
            # reference table the seed door alone opens.
            self.assertEqual((seed_languages(), seed_jurisdictions()), (Language.objects.count(), Jurisdiction.objects.count()))
            with transaction.atomic():
                tenancy.activate(self.bank.id)
                with library_write("an approved proposal", door="proposal"):
                    InstrumentTitle.objects.create(instrument=self.instrument, language_id="sv", text="Lagen", is_original=False, is_machine=True)
                with watch_write("a bank's own source"):
                    source = Source.objects.create(
                        name="door-guard.example", kind=SourceKind.objects.get(key="authority_site"), owner_tenant=self.bank
                    )
                counts = indexing.reindex(self.obligation.id)
            with transaction.atomic():
                verification = apply.apply_reverification(
                    self.obligation,
                    actor=factories.user_actor(user_id=self.checker.id),
                    verified_by=self.checker,
                    outcome="no_change",
                    note="Checked against the source.",
                    step_up_assertion_id=uuid.uuid4(),
                )
        self.assertTrue(Provision.objects.filter(pk=provision.pk).exists())
        self.assertTrue(InstrumentTitle.objects.filter(instrument=self.instrument, language_id="sv").exists())
        with transaction.atomic():
            tenancy.activate(self.bank.id)  # a bank's own source is read in its zone
            self.assertTrue(Source.objects.filter(pk=source.pk, owner_tenant=self.bank).exists())
        self.assertGreater(counts.created, 0)
        self.assertTrue(SearchChunk.objects.filter(source_id__in=self.obligation.versions.values("id")).exists())
        self.assertTrue(Verification.objects.filter(pk=verification.pk).exists())
        self.assertEqual(Obligation.objects.get(pk=self.obligation.pk).verified_by_id, self.checker.id)

    # --- every real writer, as the app role --------------------------------------------------
    def _approved(self, kind: str, payload: dict[str, Any], *, target: Obligation | None = None) -> Proposal:
        """File `kind` as a library editor's console request does, then approve it as a second
        editor's does: each in a transaction of its own, in no bank's zone, on the cw_app
        connection. `logic.approve` is what the approveProposal route calls."""
        with transaction.atomic():
            tenancy.clear_tenant()
            proposal, _ = proposals.create(
                kind=kind,
                title=f"Proven as the app role: {kind}",
                payload=payload,
                proposer=proposals.Proposer(actor=factories.user_actor(user_id=self.proposer.id), user=self.proposer),
                target_type="" if target is None else "obligation",
                target_id=None if target is None else target.id,
                field_sources=None if target is None else dict.fromkeys(("summaries.en", "summaries.sv", "effectiveFrom", "terms"), SOURCE_URL),
            )
        with transaction.atomic():
            tenancy.clear_tenant()
            return proposals.approve(
                proposal=proposals.by_id(proposal.id),
                reviewer=self.reviewer,
                actor=factories.user_actor(user_id=self.reviewer.id),
                note="",
                step_up_assertion_id=uuid.uuid4(),
            )

    def test_every_proposal_kind_is_approved_through_the_real_path_as_the_app_role(self) -> None:
        self.proposer = factories.platform_user(roles=("library_editor",), email="door-proposer@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="door-reviewer@bleqq.test")
        effective_from = timezone.localdate() + datetime.timedelta(days=30)
        decided: list[Proposal] = []
        with as_the_app_role():
            decided.append(self._approved("vocabulary_create", {"list": "flag", "key": "door_money", "labels": {"en": "Door money"}}))
            decided.append(self._approved("vocabulary_create", {"list": "flag", "key": "door_funds", "labels": {"en": "Door funds"}}))
            # The flag merged away below is on a registered change, so a merge that moves its
            # usages moves a watch row, which only the watch door reaches.
            with transaction.atomic():
                tenancy.clear_tenant()
                carried = watch_testing.term_link(watch_testing.change(), flag_key="door_funds")
            decided.append(self._approved("vocabulary_relabel", {"list": "flag", "key": "door_money", "labels": {"sv": "Dörrpengar"}}))
            decided.append(self._approved("vocabulary_retire", {"list": "flag", "key": "door_money"}))
            decided.append(self._approved("vocabulary_restore", {"list": "flag", "key": "door_money"}))
            decided.append(self._approved("vocabulary_merge", {"list": "flag", "key": "door_funds", "into": "door_money"}))
            decided.append(self._approved("term_create", {"dimension": "client_category", "key": "door_client", "labels": {"en": "Door client"}}))
            decided.append(self._approved("term_update", {"dimension": "client_category", "key": "door_client", "labels": {"sv": "Dörrklient"}}))
            decided.append(
                self._approved(
                    "new_obligation_version",
                    {
                        "summaries": {"en": "The firm assesses the client before advising.", "sv": "Företaget bedömer kunden innan rådgivning."},
                        "originalLanguage": "en",
                        "isMachine": True,
                        "effectiveFrom": effective_from.isoformat(),
                        "effectiveFromPrecision": "day",
                        "terms": ["client_category:retail"],
                    },
                    target=self.obligation,
                )
            )
        # The census: a kind added to ProposalKind fails here until it is approved above.
        self.assertEqual(
            {proposal.kind for proposal in decided},
            {kind.value for kind in ProposalKind},
            "a proposal kind not approved here as the app role: file and approve one above",
        )
        self.assertEqual({proposal.status for proposal in decided}, {ProposalStatus.APPROVED.value})
        money = Flag.objects.get(key="door_money")
        self.assertTrue(money.active)
        self.assertEqual(money.labels.get(language="sv").text, "Dörrpengar")
        self.assertFalse(Flag.objects.get(key="door_funds").active)
        self.assertTrue(ChangeTerm.objects.filter(pk=carried.pk).exists())
        term = TaxonomyTerm.objects.get(dimension__key="client_category", key="door_client")
        self.assertEqual(term.labels.get(language="sv").text, "Dörrklient")
        version = ObligationVersion.objects.get(applied_by_proposal=decided[-1])
        self.assertEqual((version.obligation_id, version.effective_from), (self.obligation.id, effective_from))
        self.assertTrue(SearchChunk.objects.filter(source_id=version.id).exists())

    def test_an_independent_agent_approves_every_vocabulary_and_term_kind_as_the_app_role(self) -> None:
        """D-79 as lifted on 2026-09-23: an agent's approval of a list or term kind writes the
        library through the proposal door as cw_app too, with the model call behind it logged
        and the machine-confirmed stamp on what it worded. One agent files, a key of another
        definition approves, each in a transaction of its own as their requests would."""
        proposing = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        confirming = agents_testing.reviewer_api_key()
        proposing_run = agents_testing.platform_run(key=proposing)
        confirming_run = agents_testing.platform_run(key=confirming)
        reviewer = proposals.Reviewer(
            actor=Actor(kind=ActorType.AGENT, id=confirming.agent.id, label=confirming.agent.key),
            api_key_id=confirming.id,
            agent_id=confirming.agent.id,
            api_key_prefix=confirming.row.key_prefix,
        )
        kinds: list[tuple[str, dict[str, Any]]] = [
            ("vocabulary_create", {"list": "flag", "key": "agent_money", "labels": {"en": "Agent money"}}),
            ("vocabulary_create", {"list": "flag", "key": "agent_funds", "labels": {"en": "Agent funds"}}),
            ("vocabulary_relabel", {"list": "flag", "key": "agent_money", "labels": {"sv": "Agentpengar"}}),
            ("vocabulary_retire", {"list": "flag", "key": "agent_money"}),
            ("vocabulary_restore", {"list": "flag", "key": "agent_money"}),
            ("vocabulary_merge", {"list": "flag", "key": "agent_funds", "into": "agent_money"}),
            ("term_create", {"dimension": "client_category", "key": "agent_client", "labels": {"en": "Agent client"}}),
            ("term_update", {"dimension": "client_category", "key": "agent_client", "labels": {"sv": "Agentklient"}}),
        ]
        decided: list[Proposal] = []
        with as_the_app_role():
            for kind, payload in kinds:
                with transaction.atomic():
                    tenancy.clear_tenant()
                    proposal, _ = proposals.create(
                        kind=kind,
                        title=f"Proven as the app role by an agent: {kind}",
                        payload=payload,
                        proposer=proposals.Proposer(
                            actor=Actor(kind=ActorType.AGENT, id=proposing.agent.id, label=proposing.agent.key),
                            api_key_id=proposing.id,
                            agent_id=proposing.agent.id,
                        ),
                        agent_run_id=proposing_run.id,
                    )
                with transaction.atomic():
                    tenancy.clear_tenant()
                    decided.append(
                        proposals.approve(
                            proposal=proposals.by_id(proposal.id),
                            reviewer=reviewer,
                            actor=reviewer.actor,
                            note="",
                            step_up_assertion_id=None,
                            decision=AgentDecision.model_validate(agents_testing.DECISION),
                            agent_run_id=confirming_run.id,
                        )
                    )
        # Every list and term kind, and nothing else: the obligation kind is proven above.
        self.assertEqual(
            {proposal.kind for proposal in decided},
            proposals.VOCABULARY_KINDS | proposals.TERM_KINDS,
            "a list or term kind not approved here by an agent as the app role",
        )
        self.assertEqual({proposal.status for proposal in decided}, {ProposalStatus.APPROVED.value})
        money = Flag.objects.get(key="agent_money")
        self.assertEqual((money.active, money.verified_origin, money.verified_by_agent_id), (True, "agent", confirming.agent.id))
        self.assertEqual({label.language: label.is_machine for label in money.labels.all()}, {"en": True, "sv": True})
        self.assertFalse(Flag.objects.get(key="agent_funds").active)
        term = TaxonomyTerm.objects.get(dimension__key="client_category", key="agent_client")
        self.assertEqual((term.verified_origin, term.verified_by_agent_id), ("agent", confirming.agent.id))
        self.assertEqual(term.labels.get(language="sv").is_machine, True)
        self.assertEqual(AiGeneration.objects.filter(agent_run=confirming_run).count(), len(kinds))

    def test_every_watch_step_writes_through_its_own_entry_point_as_the_app_role(self) -> None:
        editor = factories.platform_user(roles=("library_editor",), email="door-editor@bleqq.test")
        who = user_principal(permissions={perms.PROPOSALS_REVIEW, perms.SOURCES_MANAGE}, subject_id=editor.id)
        actor = factories.user_actor(user_id=editor.id)
        securities = watch_testing.term("regime:securities")
        proven: set[str] = set()
        with as_the_app_role():
            with transaction.atomic():
                tenancy.clear_tenant()
                status, registered = registration.register_change(
                    who=who,
                    actor=actor,
                    order=ORDER,
                    body=WatchChangeInput.model_validate(
                        {
                            "stableKey": "chg-door-guard",
                            "title": "FI adopts amended rules on paying for investment research",
                            "changeType": "adopted",
                            "authorityLabel": "Finansinspektionen",
                            "authorityCode": "fi",
                            "summary": "FI's board decided to amend three regulations in the securities area.",
                            "suggestedUrgency": "act_now",
                            "flags": ["advice_perimeter"],
                            "termIds": [str(securities.id)],
                            "sourceLabel": "Finansinspektionen",
                            "sourceUrl": SOURCE_URL,
                            "events": [{"label": "Consultation closed", "eventDate": "2026-06-01", "datePrecision": "day", "occurred": True}],
                            "documents": [{"url": f"{SOURCE_URL}en/published/news/door-guard/", "isPrimary": True}],
                            "obligationLinks": [{"obligationId": str(self.obligation.id), "confidence": 0.8}],
                        }
                    ),
                )
            proven.add("watch/registration.py")
            with transaction.atomic():
                tenancy.clear_tenant()
                curation.update_change_facts(
                    who=who,
                    actor=actor,
                    order=ORDER,
                    change_id=registered.id,
                    body=WatchChangePatch.model_validate({"keyDateLabel": "Applies from"}),
                    step_up_assertion_id=None,
                )
                curation.add_event(
                    actor=actor,
                    change_id=registered.id,
                    body=WatchChangeEventInput.model_validate({"label": "Adopted", "eventDate": "2026-06-15", "datePrecision": "day", "occurred": True}),
                )
            proven.add("watch/curation.py")
            with transaction.atomic():
                tenancy.clear_tenant()
                so_what_draft.store(
                    RegulatoryChange.objects.get(pk=registered.id), WatchSoWhatInput.model_validate(SO_WHAT), actor=actor, agent_run_id=None
                )
            proven.add("watch/so_what_draft.py")
            with transaction.atomic():
                tenancy.clear_tenant()
                source = sources.create_source(
                    actor=actor,
                    order=ORDER,
                    body=WatchSourceInput.model_validate({"name": "Door guard news", "url": f"{SOURCE_URL}en/published/news/", "kind": "authority_site", "checkFrequency": "daily"}),
                )
            proven.add("watch/sources.py")
        # The census: a module allowed to open the watch door fails here until one of its
        # entry points is proven above as the app role.
        self.assertEqual(
            proven,
            set(WATCH_WRITE_ALLOWLIST) - {"watch/write.py"},
            "a module that may open the watch door is not proven here as the app role: call one of its entry points above",
        )
        self.assertEqual(status, 201)
        change = RegulatoryChange.objects.get(pk=registered.id)
        self.assertEqual((change.key_date_label, change.so_what_draft), ("Applies from", SO_WHAT["text"]))
        self.assertEqual(sorted(change.events.values_list("label", flat=True)), ["Adopted", "Consultation closed"])
        self.assertEqual(change.documents.count(), 1)
        self.assertTrue(change.term_links.filter(flag__key="advice_perimeter").exists())
        self.assertTrue(change.term_links.filter(term=securities).exists())
        self.assertTrue(ChangeObligation.objects.filter(change=change, obligation=self.obligation).exists())
        self.assertTrue(Source.objects.filter(pk=source.id, owner_tenant__isnull=True).exists())


class EachDoorNamesItselfAndPutsBackTheOneItFound(TestCase):
    """What the doors set, observed on the connection they write through."""

    def test_the_doors_nest_and_each_puts_back_the_door_it_found(self) -> None:
        self.assertEqual(open_door(), "")
        with library_write("a reference seed"):
            self.assertEqual(open_door(), "seed")
            with library_write("an approved proposal", door="proposal"):
                self.assertEqual(open_door(), "proposal")
                with indexing.index_write("the rebuild the approval runs"):
                    self.assertEqual(open_door(), "index")
                self.assertEqual(open_door(), "proposal")
                with watch_write("a change a run sighted"):
                    self.assertEqual(open_door(), "watch")
                self.assertEqual(open_door(), "proposal")
            self.assertEqual(open_door(), "seed")
        self.assertEqual(open_door(), "")

    def test_a_door_left_by_an_exception_is_put_back_by_the_rollback(self) -> None:
        with library_write("an approved proposal", door="proposal"):
            with self.assertRaises(RuntimeError), indexing.index_write("a rebuild that fails"):
                self.assertEqual(open_door(), "index")
                raise RuntimeError("the rebuild failed")
            self.assertEqual(open_door(), "proposal")
            self.assertIsNotNone(tenancy.library_write_reason())
        self.assertEqual(open_door(), "")
        self.assertIsNone(tenancy.library_write_reason())

    def test_the_re_verification_stamp_writes_through_its_own_door(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
        checker = factories.user()
        obligation = library_testing.obligation(
            library_testing.instrument(key="stamp-door-act", regime="regime:securities"), key="stamp-door-act/1"
        )
        seen: list[str] = []
        with mock.patch.object(apply, "record", side_effect=lambda **_: seen.append(open_door())):
            apply.apply_reverification(
                obligation,
                actor=factories.user_actor(user_id=checker.id),
                verified_by=checker,
                outcome="no_change",
                note="",
                step_up_assertion_id=uuid.uuid4(),
            )
        self.assertEqual(seen, ["reverification"])
        self.assertEqual(open_door(), "")

    def test_a_door_refuses_a_blank_reason_and_opens_nothing(self) -> None:
        with self.assertRaises(ValueError), library_write("   ", door="proposal"):
            pass
        self.assertEqual(open_door(), "")
