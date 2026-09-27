"""The weekly digest's beat (COL-02, CHUNK10_TASKS `c10-digest-b`;
`c10-digest-beat-and-journeys`).

What these pin:

- **The bank's day and hour.** Fired every hour of a whole week in UTC, the beat hands a bank
  on once: at `DIGEST_SEND_HOUR` on its own clock, on its own `digest_weekday`. A bank whose
  day has not come gets nothing, and one in another zone is served at its own local hour.
- **Once a week.** A second round the same week sends nothing more.
- **Counts only.** The fan-out logs how many banks it handed on, never a name or an address.
- **Registered.** The entry is on the beat schedule and the per-bank task is a `@tenant_task`.

Every date is the bank's local today plus an offset (CHUNK10_TASKS rule 14).
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import TestCase

from apps.collab import tasks
from apps.collab.models import EmailMessage
from apps.collab.tests_reminders import at, frozen
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.reading import today_for
from apps.shared import factories, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import Tenant, Weekday
from apps.shared.tenancy import is_tenant_task
from apps.watch import testing as watch_build

STOCKHOLM, HELSINKI = "Europe/Stockholm", "Europe/Helsinki"


class DigestBeat(TestCase):
    """Two banks: Stockholm sends on the weekday two days after its today, Helsinki on the
    weekday four days after. Each has one member with a register entry under review."""

    stockholm: Tenant
    helsinki: Tenant
    anna: User
    aino: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        on = library_build.instrument(key="inst-digest-beat", regime="regime:securities")
        cls.stockholm = factories.tenant(slug="digest-beat-se", timezone=STOCKHOLM)
        cls.helsinki = factories.tenant(slug="digest-beat-fi", timezone=HELSINKI)
        for tenant, offset, attribute in ((cls.stockholm, 2, "anna"), (cls.helsinki, 4, "aino")):
            day = today_for(tenant) + datetime.timedelta(days=offset)
            Tenant.objects.filter(pk=tenant.pk).update(digest_weekday=list(Weekday)[day.weekday()].value)
            person = factories.member_user(tenant, roles=("contributor",))
            obligation = library_build.obligation(on, key=f"obl-digest-beat-{tenant.slug}")
            factories.register_entry(
                tenant, obligation.id, first_line_owner=person, next_review_date=day + datetime.timedelta(days=5)
            )
            setattr(cls, attribute, person)

    def setUp(self) -> None:
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)

    def digests(self, tenant: Tenant) -> list[datetime.datetime]:
        tenancy.activate(tenant.id)
        rows = EmailMessage.objects.filter(template="weekly_digest").exclude(sent_at=None).order_by("sent_at")
        return [row.sent_at for row in rows if row.sent_at is not None]

    def test_each_bank_gets_one_round_at_its_own_hour_on_its_own_day_in_a_week_of_hourly_beats(self) -> None:
        anchor = today_for(self.stockholm)
        start = at(anchor, 0, STOCKHOLM).astimezone(datetime.UTC)
        fired: dict[str, list[datetime.datetime]] = {}
        for hour in range(8 * 24):
            moment = start + datetime.timedelta(hours=hour)
            with frozen(moment):
                tasks.send_digests()
            for tenant in (self.stockholm, self.helsinki):
                if len(self.digests(tenant)) > len(fired.setdefault(tenant.slug, [])):
                    fired[tenant.slug].append(moment)
        for tenant, zone in ((self.stockholm, STOCKHOLM), (self.helsinki, HELSINKI)):
            with self.subTest(bank=tenant.slug):
                (moment,) = fired[tenant.slug]
                tenant.refresh_from_db()
                local = moment.astimezone(ZoneInfo(zone))
                self.assertEqual(local.hour, settings.DIGEST_SEND_HOUR)
                self.assertEqual(list(Weekday)[local.weekday()].value, tenant.digest_weekday)
        self.assertEqual(sorted(mailed.to for mailed in MockMailer.sent), sorted([self.anna.email, self.aino.email]))

    def test_a_bank_whose_day_has_not_come_gets_nothing_and_a_second_round_the_same_week_sends_nothing(self) -> None:
        anchor = today_for(self.stockholm)
        with frozen(at(anchor + datetime.timedelta(days=1), settings.DIGEST_SEND_HOUR, STOCKHOLM)):
            tasks.send_digests()
        self.assertEqual(MockMailer.sent, [])
        for _ in range(2):
            with frozen(at(anchor + datetime.timedelta(days=2), settings.DIGEST_SEND_HOUR, STOCKHOLM)):
                tasks.send_digests()
        self.assertEqual([mailed.to for mailed in MockMailer.sent], [self.anna.email])
        self.assertEqual(len(self.digests(self.stockholm)), 1)

    def test_the_fan_out_logs_the_count_of_banks_and_nothing_else(self) -> None:
        anchor = today_for(self.stockholm)
        with self.assertLogs("apps.collab.tasks", level="INFO") as captured:
            with frozen(at(anchor + datetime.timedelta(days=2), settings.DIGEST_SEND_HOUR, STOCKHOLM)):
                tasks.send_digests()
        (line,) = [record for record in captured.records if record.msg.startswith("collab digests")]
        self.assertEqual(line.getMessage(), "collab digests handed on for 1 banks")
        joined = " ".join(record.getMessage() for record in captured.records)
        for leak in (self.anna.email, self.stockholm.slug, str(self.stockholm.id)):
            self.assertNotIn(leak, joined)

    def test_the_entry_is_on_the_beat_and_the_bank_task_is_a_tenant_task(self) -> None:
        entry = settings.CELERY_BEAT_SCHEDULE["collab-digests"]
        self.assertEqual(entry["task"], "apps.collab.tasks.send_digests")
        self.assertTrue(is_tenant_task(tasks.send_tenant_digests.run))
