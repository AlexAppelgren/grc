"""The home tables (HOM-02, HOM-04; schema v0.3 `briefing`, `briefing_item`,
`calendar_feed`; INPUT_DELTAS §9).

Three tenant tables and nothing shared: what one bank was told about a week, which cases
that telling named, and the calendar addresses its people subscribed with. These tests pin
the two properties the rest of chunk 6 is allowed to rely on without checking again.

**A sent briefing cannot be rewritten.** HOM-S3's last line — "a later change to the feed
does not alter the snapshot" — is a database fact here, not a promise the briefing job
keeps: `briefing_item` refuses an update and a delete in Python and in PostgreSQL, from the
application role as well as from the runner's own. `c6-briefing-backend` may therefore write
a snapshot and stop worrying about it.

**A calendar address is a credential the system cannot hand back.** Only a SHA-256 hash is
stored, under a unique index; no column, `__str__` or `__repr__` can produce the address a
person pasted into their calendar. The test below reads the model's own field list rather
than trusting the docstring, so a later column called `token` fails here.

The briefing row itself is deliberately not a ledger: `email_sent_at` is stamped when the
mail goes out, which is the one thing about a snapshot that is not known when the snapshot
is taken. That is proved too, so nobody turns it into an append-only table later and finds
the weekly job unable to say the mail was sent.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.cases import testing as case_build
from apps.home.models import Briefing, BriefingItem, CalendarFeed, FeedFilter
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.shared import factories, tenancy
from apps.shared.audit import AppendOnlyRefused
from apps.shared.models import Tenant
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.watch import testing as watch_build

# A Monday, and the Monday before it. Fixed dates, never derived from the real clock: a
# briefing is addressed by its week, and a fixture that moved with today would make these
# tests pass or fail by the day they ran (CLAUDE.md §8.3).
WEEK = datetime.date(2026, 9, 14)
WEEK_BEFORE = datetime.date(2026, 9, 7)
# The right length for what `hashlib.sha256(...).hexdigest()` produces (64 characters), and
# nothing else: a realistic-looking hex digest is exactly the shape a secret scanner cannot
# tell from a real credential, and a fixture that has to be allowlisted teaches the scanner
# to ignore that shape everywhere. Two of them, because one test needs a second subscription.
TOKEN_HASH = "a" * 64
OTHER_HASH = "b" * 64
# What a column, a repr or a log line must never be able to produce. No builder puts it
# anywhere: the tests assert its absence from everything the model can show.
PLAINTEXT = "feed-token-" + "x" * 32


def seed_reference() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()
    seed_authorities()


def briefing(tenant: Tenant, *, week_start: datetime.date = WEEK) -> Briefing:
    """One week's snapshot, written with its tenant activated: FORCE ROW LEVEL SECURITY
    applies to the test runner's own connection too, so a tenant row is invisible and
    unwritable until `tenancy.activate()` has run inside the transaction (playbook 14)."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return Briefing.objects.create(tenant=tenant, week_start=week_start)


def calendar_feed(tenant: Tenant, *, token_hash: str = TOKEN_HASH) -> CalendarFeed:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return CalendarFeed.objects.create(
            tenant=tenant,
            user=factories.member_user(tenant),
            token_hash=token_hash,
            filter=FeedFilter.REGULATORY.value,
        )


class HomeZoneTestCase(TestCase):
    """Builders the home tests share: two banks, a library change and one bank's case for
    it, because a briefing item points at a case and a case is the bank's own."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()

    def setUp(self) -> None:
        self.tenant_a = factories.tenant(slug=f"home-a-{uuid.uuid4().hex[:8]}")
        self.tenant_b = factories.tenant(slug=f"home-b-{uuid.uuid4().hex[:8]}")
        self.change = watch_build.change()
        self.case_a = case_build.case(self.tenant_a, self.change)

    def item(self, row: Briefing, *, rank: int = 1, case: Any = None) -> BriefingItem:
        with transaction.atomic():
            tenancy.activate(row.tenant_id)
            return BriefingItem.objects.create(
                tenant_id=row.tenant_id, briefing=row, case=case if case is not None else self.case_a, rank=rank
            )


class BriefingRows(HomeZoneTestCase):
    def test_a_week_has_one_briefing_per_bank(self) -> None:
        """Re-running the weekly job for a week that already has a snapshot must send
        nothing and write nothing; the constraint is what makes that cheap to write."""
        briefing(self.tenant_a)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            with self.assertRaises(IntegrityError):
                Briefing.objects.create(tenant=self.tenant_a, week_start=WEEK)

    def test_two_banks_each_have_their_own_briefing_for_one_week(self) -> None:
        self.assertNotEqual(briefing(self.tenant_a).id, briefing(self.tenant_b).id)

    def test_the_newest_week_comes_first(self) -> None:
        briefing(self.tenant_a, week_start=WEEK_BEFORE)
        newest = briefing(self.tenant_a, week_start=WEEK)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            self.assertEqual(Briefing.objects.first(), newest)
        # What a shell, an error page or a log line would show: the bank and the week, never
        # a title and never a word of the briefing itself (playbook 4.7).
        self.assertEqual(str(newest), f"{self.tenant_a.id}:{WEEK}")

    def test_the_briefing_row_is_stamped_when_the_mail_goes_out(self) -> None:
        """The snapshot's items are frozen; the moment it was sent is not known when it is
        written, so the briefing row itself is not a ledger."""
        row = briefing(self.tenant_a)
        self.assertIsNone(row.email_sent_at)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            row.email_sent_at = timezone.now()
            row.save(update_fields=["email_sent_at"])
            self.assertIsNotNone(Briefing.objects.get(pk=row.pk).email_sent_at)


class BriefingItemRows(HomeZoneTestCase):
    def test_a_case_appears_once_in_a_week(self) -> None:
        row = briefing(self.tenant_a)
        self.item(row, rank=1)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            with self.assertRaises(IntegrityError):
                BriefingItem.objects.create(tenant=self.tenant_a, briefing=row, case=self.case_a, rank=2)

    def test_the_lead_is_rank_one_and_comes_first(self) -> None:
        row = briefing(self.tenant_a)
        second = case_build.case(self.tenant_a, watch_build.change())
        self.item(row, rank=2, case=second)
        lead = self.item(row, rank=1)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            self.assertEqual(BriefingItem.objects.first(), lead)
        self.assertEqual(str(lead), f"{row.id}:1", "a repr names the row, never the case's title")

    def test_python_refuses_to_rewrite_a_sent_briefing(self) -> None:
        row = briefing(self.tenant_a)
        item = self.item(row)
        item.rank = 9
        with self.assertRaises(AppendOnlyRefused):
            item.save()
        with self.assertRaises(AppendOnlyRefused):
            item.delete()
        with self.assertRaises(AppendOnlyRefused):
            BriefingItem.objects.filter(pk=item.pk).update(rank=9)
        with self.assertRaises(AppendOnlyRefused):
            BriefingItem.objects.filter(pk=item.pk).delete()

    def test_the_database_trigger_refuses_it_too(self) -> None:
        """Python is the ORM's promise; the trigger is everyone's. A fix that meant it would
        say so with `SET LOCAL cw.maintenance` in a migration, as the schema owner."""
        row = briefing(self.tenant_a)
        item = self.item(row)
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            with self.assertRaises(DatabaseError) as caught, transaction.atomic():
                tenancy.activate(self.tenant_a.id)
                cursor.execute("UPDATE briefing_item SET rank = 9 WHERE id = %s", [str(item.id)])
            self.assertIn("append-only", str(caught.exception))
            with self.assertRaises(DatabaseError), transaction.atomic():
                tenancy.activate(self.tenant_a.id)
                cursor.execute("DELETE FROM briefing_item WHERE id = %s", [str(item.id)])


class CalendarFeedRows(HomeZoneTestCase):
    def test_one_subscription_per_stored_hash(self) -> None:
        """The hash is what the ICS route looks a token up by, so two rows sharing one would
        make a single address answer for two subscriptions. The index is global and not per
        bank, so a collision across two banks is refused as well."""
        calendar_feed(self.tenant_a)
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            with self.assertRaises(IntegrityError):
                CalendarFeed.objects.create(
                    tenant=self.tenant_b, user=factories.member_user(self.tenant_b), token_hash=TOKEN_HASH
                )

    def test_no_column_holds_a_plaintext_address(self) -> None:
        """Read off the model rather than off the docstring: a later column named `token`,
        `secret` or `url` would fail here rather than in a log file."""
        names = {field.name for field in CalendarFeed._meta.get_fields()}
        self.assertIn("token_hash", names)
        self.assertEqual(names & {"token", "secret", "url", "address", "plain_key"}, set())

    def test_nothing_the_model_can_print_carries_the_address_or_its_hash(self) -> None:
        feed = calendar_feed(self.tenant_a)
        for shown in (str(feed), repr(feed)):
            self.assertNotIn(PLAINTEXT, shown)
            self.assertNotIn(TOKEN_HASH, shown)
        self.assertEqual(str(feed), str(feed.id))

    def test_the_newest_subscription_comes_first_and_revoking_keeps_the_row(self) -> None:
        calendar_feed(self.tenant_a)
        newest = calendar_feed(self.tenant_a, token_hash=OTHER_HASH)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            self.assertEqual(CalendarFeed.objects.first(), newest)
            newest.revoked_at = timezone.now()
            newest.save(update_fields=["revoked_at"])
            self.assertEqual(CalendarFeed.objects.count(), 2, "revoking stamps the row, it never deletes it")

    def test_the_default_subscription_carries_everything(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            feed = CalendarFeed.objects.create(
                tenant=self.tenant_a, user=factories.member_user(self.tenant_a), token_hash=OTHER_HASH
            )
        self.assertEqual(feed.filter, FeedFilter.ALL.value)


class HomeRowsUnderTheApplicationRole(TransactionTestCase):
    """The same two rules proved for `cw_app`, the role the application actually runs as:
    it owns nothing and cannot bypass row-level security (ADR 0022). A `TransactionTestCase`
    because the proof needs committed rows visible across two connections."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        # A TransactionTestCase does not wrap the test in one, and the reference seeds audit
        # every row they write, so record() needs a transaction opened here.
        with transaction.atomic():
            seed_reference()
        self.tenant_a = factories.tenant(slug=f"home-app-a-{uuid.uuid4().hex[:8]}")
        self.tenant_b = factories.tenant(slug=f"home-app-b-{uuid.uuid4().hex[:8]}")
        self.briefing = briefing(self.tenant_a)
        self.case = case_build.case(self.tenant_a, watch_build.change())

    def test_another_banks_briefing_is_not_there_at_all(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            self.assertEqual(Briefing.objects.using("app").count(), 0)
            self.assertEqual(CalendarFeed.objects.using("app").count(), 0)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self.assertEqual(Briefing.objects.using("app").count(), 1)

    def test_the_application_role_may_add_a_briefing_item_and_never_change_one(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            item = BriefingItem.objects.using("app").create(
                tenant_id=self.tenant_a.id, briefing=self.briefing, case=self.case, rank=1
            )
        with connections["app"].cursor() as cursor:
            with self.assertRaises(DatabaseError) as caught, transaction.atomic(using="app"):
                tenancy.activate(self.tenant_a.id, using="app")
                cursor.execute("UPDATE briefing_item SET rank = 9 WHERE id = %s", [str(item.id)])
            self.assertIn("append-only", str(caught.exception))
            with self.assertRaises(DatabaseError), transaction.atomic(using="app"):
                tenancy.activate(self.tenant_a.id, using="app")
                cursor.execute("DELETE FROM briefing_item WHERE id = %s", [str(item.id)])

    def test_the_escape_hatch_is_the_schema_owners_and_not_the_applications(self) -> None:
        """`SET LOCAL cw.maintenance` states a conscious fix, and the guard honours it only
        for the migrator. A stray or injected one in request code switches nothing off."""
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            item = BriefingItem.objects.using("app").create(
                tenant_id=self.tenant_a.id, briefing=self.briefing, case=self.case, rank=1
            )
        with connections["app"].cursor() as cursor:
            with self.assertRaises(DatabaseError), transaction.atomic(using="app"):
                tenancy.activate(self.tenant_a.id, using="app")
                cursor.execute("SET LOCAL cw.maintenance = 'on'")
                cursor.execute("UPDATE briefing_item SET rank = 9 WHERE id = %s", [str(item.id)])
