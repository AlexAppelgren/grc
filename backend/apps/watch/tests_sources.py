"""The source registry and the coverage log (WAT-01, AGT-01, ADM-02, AUD-01).

What is proved here, over the real routes: a library editor keeps the registry and an
agent's key never can; a run logs what it checked against a run it has open and nothing
else; the coverage page computes staleness from the log rather than storing it, reads it in
a fixed number of queries however many sources there are, and counts sweeps only — a run
full of re-checks must never make a source look fresh.

The checks are filed with a real key (`X-API-Key`), never a stubbed principal, so the
resolver, row-level security and the mixed write rule all run as they do in production. The
registry writes take a stubbed console session, because a library editor's sign-in is
`apps/identity`'s to prove and what matters here is the permission in front of the write.

Every threshold the stale rule uses is overridden with `override_settings` rather than
written into an assertion, so a test states the rule and never the number (playbook 4.3).

Proven to fail 2026-09-21 against the declared contract: every test below answered 501
`not_built` before `sources.py` was written.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.agents.models import RunStatus
from apps.library.models import Authority, SubjectType
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase, stub_session, user_principal
from apps.watch import sources as sources_logic
from apps.watch import testing as watch_build
from apps.watch.models import CheckFrequency, CheckStatus, SourceCheckKind

SOURCES = "/api/v1/sources"
COVERAGE = "/api/v1/sources/coverage"
JSON = "application/json"

NEW_SOURCE = {
    "name": "Finansinspektionen news",
    "url": "https://www.fi.se/en/published/news/",
    "kind": "authority_site",
    "checkFrequency": "daily",
}


class WatchSourceCase(ScenarioTestCase):
    """The reference rows every registry test needs, and a platform key with a run open."""

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        # A console session and a platform key both work in the library's zone: the mixed
        # write rule accepts a library row only from a session that is in it (H15).
        tenancy.clear_tenant()
        self.key = agent_build.agent_key()
        # A real person behind the console session: the audit row names who registered a
        # source, so a stubbed principal with no user row is not a session this can use.
        self.editor = factories.platform_user(email="library.editor@bleqq.example")

    def as_editor(self) -> Any:
        return stub_session(user_principal(permissions={perms.SOURCES_MANAGE}, subject_id=self.editor.id))

    def as_reader(self) -> Any:
        return stub_session(user_principal(permissions={perms.WATCH_READ}, tenant_id=uuid.uuid4()))

    def session_headers(self) -> dict[str, Any]:
        return self.as_user(user_principal())

    def register(self, body: dict[str, Any] | None = None) -> Any:
        with self.as_editor():
            return self.client.post(SOURCES, data=body or NEW_SOURCE, content_type=JSON, **self.session_headers())

    def log_check(self, run: Any, body: dict[str, Any], *, plain: str | None = None) -> Any:
        return self.client.post(
            f"/api/v1/agent-runs/{run.id}/source-checks",
            data=body,
            content_type=JSON,
            HTTP_X_API_KEY=plain or self.key.plain_key,
        )

    def coverage(self) -> list[dict[str, Any]]:
        with self.as_reader():
            response = self.client.get(COVERAGE, **self.session_headers())
        self.assertEqual(response.status_code, 200, response.content)
        return list(response.json())


class SourceRegistry(WatchSourceCase):
    """POST /sources and PATCH /sources/{sourceId}: a library editor's, never a key's."""

    def test_an_editor_registers_a_source_and_it_appears_in_the_registry(self) -> None:
        response = self.register({**NEW_SOURCE, "authorityId": str(Authority.objects.get(key="fi").id)})
        self.assertEqual(response.status_code, 201, response.content)
        row = response.json()
        self.assertEqual(row["name"], NEW_SOURCE["name"])
        self.assertEqual(row["kind"]["key"], "authority_site")
        self.assertEqual(row["checkFrequency"], "daily")
        self.assertTrue(row["active"], "a source is registered with automated checks on")

        with self.as_reader():
            listed = self.client.get(SOURCES, **self.session_headers())
        self.assertEqual([entry["name"] for entry in listed.json()], [NEW_SOURCE["name"]])

    def test_registering_a_source_writes_its_audit_and_outbox_rows(self) -> None:
        self.register()
        event = AuditEvent.objects.filter(action=sources_logic.REGISTERED).first()
        assert event is not None
        self.assertEqual(event.subject_type, "source")
        self.assertIsNone(event.tenant_id, "the registry is a library fact and belongs to no bank")
        self.assertEqual(event.after["name"], NEW_SOURCE["name"])
        self.assertTrue(OutboxEvent.objects.filter(audit_event=event).exists())

    def test_a_second_source_of_the_same_name_is_refused(self) -> None:
        self.assertEqual(self.register().status_code, 201)
        response = self.register({**NEW_SOURCE, "url": "https://www.fi.se/"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "duplicate_key")
        self.assertEqual(len(sources_logic.list_sources(["en"])), 1, "the refusal stored nothing")

    def test_a_kind_or_an_authority_the_library_does_not_hold_is_refused_and_stores_nothing(self) -> None:
        cases = [
            {**NEW_SOURCE, "kind": "authorety_site"},
            {**NEW_SOURCE, "authorityId": str(uuid.uuid4())},
        ]
        for body in cases:
            with self.subTest(body=sorted(body)):
                response = self.register(body)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "unknown_key")
        self.assertEqual(sources_logic.list_sources(["en"]), [])

    def test_the_refusal_for_an_unknown_kind_lists_the_keys_an_editor_may_send(self) -> None:
        problem = self.register({**NEW_SOURCE, "kind": "authorety_site"}).json()
        self.assertIn("authority_site", problem["validKeys"])
        self.assertEqual(problem["vocabulary"], "source_kind")

    def test_an_editor_moves_a_source_and_switches_its_checks_off(self) -> None:
        source = watch_build.source(name="fi.se news", check_frequency=CheckFrequency.DAILY)
        with self.as_editor():
            response = self.client.patch(
                f"{SOURCES}/{source.id}",
                data={"url": "https://www.fi.se/en/published/news/", "checkFrequency": "weekly", "active": False},
                content_type=JSON,
                **self.session_headers(),
            )
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()
        self.assertEqual(row["url"], "https://www.fi.se/en/published/news/")
        self.assertEqual(row["checkFrequency"], "weekly")
        self.assertFalse(row["active"])
        event = AuditEvent.objects.filter(action=sources_logic.UPDATED).first()
        assert event is not None
        self.assertEqual(event.before["checkFrequency"], "daily")
        self.assertEqual(event.after["checkFrequency"], "weekly")

    def test_a_field_left_out_is_left_alone(self) -> None:
        source = watch_build.source(name="fi.se news", check_frequency=CheckFrequency.DAILY)
        with self.as_editor():
            response = self.client.patch(
                f"{SOURCES}/{source.id}", data={"active": False}, content_type=JSON, **self.session_headers()
            )
        row = response.json()
        self.assertEqual(row["checkFrequency"], "daily")
        self.assertEqual(row["url"], "https://www.fi.se/")

    def test_a_source_that_is_not_there_is_404(self) -> None:
        with self.as_editor():
            response = self.client.patch(
                f"{SOURCES}/{uuid.uuid4()}", data={"active": False}, content_type=JSON, **self.session_headers()
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_no_key_scope_registers_or_changes_a_source(self) -> None:
        """WAT-01: the registry is a person's. A key holding every watch scope still gets no
        session, so both writes answer 401 rather than reaching the logic."""
        source = watch_build.source(name="fi.se news")
        created = self.client.post(SOURCES, data=NEW_SOURCE, content_type=JSON, HTTP_X_API_KEY=self.key.plain_key)
        changed = self.client.patch(
            f"{SOURCES}/{source.id}", data={"active": False}, content_type=JSON, HTTP_X_API_KEY=self.key.plain_key
        )
        self.assertEqual((created.status_code, changed.status_code), (401, 401))
        source.refresh_from_db()
        self.assertTrue(source.active)


class SourceCheckLog(WatchSourceCase):
    """POST /agent-runs/{runId}/source-checks: one line of the coverage log per look."""

    def test_a_run_logs_a_check_of_a_registered_source(self) -> None:
        source = watch_build.source(name="fi.se news")
        run = agent_build.platform_run(key=self.key)
        response = self.log_check(run, {"sourceName": source.name, "status": "ok", "itemsFound": 3})
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(response.content, b"")
        check = source.checks.get()
        self.assertEqual((check.status, check.items_found, check.kind), ("ok", 3, SourceCheckKind.SWEEP.value))
        self.assertEqual(check.agent_run_id, run.id)

    def test_the_line_carries_its_audit_and_outbox_rows_with_the_agent_as_actor(self) -> None:
        source = watch_build.source(name="fi.se news")
        self.log_check(agent_build.platform_run(key=self.key), {"sourceName": source.name, "status": "ok"})
        event = AuditEvent.objects.filter(action=sources_logic.CHECK_LOGGED).first()
        assert event is not None
        self.assertEqual(event.actor_type, "agent")
        self.assertEqual(event.actor_label, self.key.agent.key)
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.after["source"], source.name)
        self.assertTrue(OutboxEvent.objects.filter(audit_event=event).exists())

    def test_finding_nothing_is_a_result_and_is_still_logged(self) -> None:
        source = watch_build.source(name="fi.se news")
        response = self.log_check(
            agent_build.platform_run(key=self.key), {"sourceName": source.name, "status": "ok", "itemsFound": 0}
        )
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(source.checks.get().items_found, 0)

    def test_an_unknown_source_is_refused_and_logs_nothing(self) -> None:
        run = agent_build.platform_run(key=self.key)
        response = self.log_check(run, {"sourceName": "a source nobody registered", "status": "ok"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "unknown_source")
        self.assertEqual(run.source_checks.count(), 0)

    def test_a_closed_run_is_refused_and_logs_nothing(self) -> None:
        source = watch_build.source(name="fi.se news")
        run = agent_build.platform_run(key=self.key)
        run.status = RunStatus.SUCCEEDED.value
        run.save(update_fields=["status"])
        response = self.log_check(run, {"sourceName": source.name, "status": "ok"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "run_not_open")
        self.assertEqual(source.checks.count(), 0)

    def test_another_keys_run_is_404_so_a_run_id_cannot_be_probed_for(self) -> None:
        source = watch_build.source(name="fi.se news")
        run = agent_build.platform_run(key=self.key)
        other = agent_build.agent_key(agent_row=self.key.agent)
        response = self.log_check(run, {"sourceName": source.name, "status": "ok"}, plain=other.plain_key)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")
        self.assertEqual(source.checks.count(), 0)

    def test_a_failed_check_says_what_went_wrong_and_counts_nothing(self) -> None:
        source = watch_build.source(name="fi.se news")
        run = agent_build.platform_run(key=self.key)
        silent = self.log_check(run, {"sourceName": source.name, "status": "failed"})
        self.assertEqual(silent.status_code, 422)
        self.assertEqual(silent.json()["code"], "validation_error")

        told = self.log_check(
            run, {"sourceName": source.name, "status": "failed", "itemsFound": 9, "error": "502 from the publisher"}
        )
        self.assertEqual(told.status_code, 204, told.content)
        check = source.checks.get()
        self.assertEqual(check.items_found, 0, "a fetch that failed read nothing, whatever it reported")
        self.assertEqual(check.error, "502 from the publisher")

    def test_a_successful_check_carries_no_error(self) -> None:
        source = watch_build.source(name="fi.se news")
        response = self.log_check(
            agent_build.platform_run(key=self.key), {"sourceName": source.name, "status": "ok", "error": "none, really"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_a_recheck_names_the_library_record_it_looked_at(self) -> None:
        source = watch_build.source(name="fi.se news")
        run = agent_build.platform_run(key=self.key)
        subject = uuid.uuid4()
        response = self.log_check(
            run,
            {
                "sourceName": source.name,
                "status": "ok",
                "kind": "recheck",
                "subjectType": "obligation",
                "subjectId": str(subject),
            },
        )
        self.assertEqual(response.status_code, 204, response.content)
        check = source.checks.get()
        self.assertEqual((check.kind, check.subject_type, check.subject_id), ("recheck", "obligation", subject))

    def test_a_recheck_without_a_subject_and_a_sweep_with_one_are_both_refused(self) -> None:
        source = watch_build.source(name="fi.se news")
        run = agent_build.platform_run(key=self.key)
        cases = [
            {"sourceName": source.name, "status": "ok", "kind": "recheck"},
            {"sourceName": source.name, "status": "ok", "subjectType": "obligation", "subjectId": str(uuid.uuid4())},
        ]
        for body in cases:
            with self.subTest(kind=body.get("kind", "sweep")):
                response = self.log_check(run, body)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(source.checks.count(), 0)


@override_settings(SOURCE_STALE_AFTER_CHECKS=1, SOURCE_STALE_GRACE_HOURS=24)
class SourceCoverage(WatchSourceCase):
    """GET /sources/coverage: the stale rule, computed from the log and never stored."""

    def test_a_source_nobody_has_checked_reads_never_and_is_not_overdue(self) -> None:
        watch_build.source(name="fi.se news")
        row = self.coverage()[0]
        self.assertEqual(row["lastStatus"], "never")
        self.assertIsNone(row["lastCheckedAt"])
        self.assertFalse(row["overdue"], "with no log there is nothing to measure")

    def test_the_log_keeps_both_checks_and_the_page_shows_the_last(self) -> None:
        source = watch_build.source(name="fi.se news")
        run = agent_build.platform_run(key=self.key)
        now = timezone.now()
        watch_build.source_check(
            source, run=run, status=CheckStatus.OK, items_found=0, checked_at=now - datetime.timedelta(hours=2)
        )
        watch_build.source_check(
            source,
            run=run,
            status=CheckStatus.FAILED,
            error="502 from the publisher",
            checked_at=now - datetime.timedelta(hours=1),
        )
        logged = list(source.checks.all())
        self.assertEqual([check.status for check in logged], ["failed", "ok"], "newest first, both kept")
        self.assertEqual({check.agent_run_id for check in logged}, {run.id}, "each line names the run behind it")

        row = self.coverage()[0]
        self.assertEqual(row["lastStatus"], "failed")
        self.assertEqual(row["lastError"], "502 from the publisher")
        self.assertTrue(row["overdue"], "the most recent sweep failed, which is the whole default rule")

    @override_settings(SOURCE_STALE_AFTER_CHECKS=2)
    def test_how_many_failures_make_a_source_stale_is_a_setting(self) -> None:
        source = watch_build.source(name="fi.se news")
        now = timezone.now()
        watch_build.source_check(source, status=CheckStatus.OK, checked_at=now - datetime.timedelta(hours=3))
        watch_build.source_check(
            source, status=CheckStatus.FAILED, error="502", checked_at=now - datetime.timedelta(hours=2)
        )
        self.assertFalse(self.coverage()[0]["overdue"], "one failure is not yet two")

        watch_build.source_check(
            source, status=CheckStatus.FAILED, error="502", checked_at=now - datetime.timedelta(hours=1)
        )
        self.assertTrue(self.coverage()[0]["overdue"])

    def test_a_source_checked_longer_ago_than_its_cadence_allows_is_overdue(self) -> None:
        source = watch_build.source(name="fi.se news", check_frequency=CheckFrequency.DAILY)
        watch_build.source_check(source, status=CheckStatus.OK, checked_at=timezone.now() - datetime.timedelta(days=3))
        self.assertTrue(self.coverage()[0]["overdue"])

    def test_the_grace_on_top_of_the_cadence_is_a_setting(self) -> None:
        source = watch_build.source(name="fi.se news", check_frequency=CheckFrequency.DAILY)
        watch_build.source_check(source, status=CheckStatus.OK, checked_at=timezone.now() - datetime.timedelta(hours=50))
        self.assertTrue(self.coverage()[0]["overdue"], "a daily source two days unswept is past a grace of a day")
        with override_settings(SOURCE_STALE_GRACE_HOURS=48):
            self.assertFalse(self.coverage()[0]["overdue"], "the same log, a wider grace, and the row is clean")

    def test_a_deactivated_source_is_listed_and_never_reported_stale(self) -> None:
        """It gets no automated check, so calling it stale would fill the page with rows
        nobody can act on."""
        source = watch_build.source(name="fi.se news", active=False)
        watch_build.source_check(source, status=CheckStatus.FAILED, error="502")
        row = self.coverage()[0]
        self.assertFalse(row["source"]["active"])
        self.assertEqual(row["lastStatus"], "failed", "the log it already has is still shown")
        self.assertFalse(row["overdue"])

    def test_a_run_full_of_rechecks_never_makes_a_source_look_fresh(self) -> None:
        """Only sweeps count: a re-check looks again at a record the source already gave us
        and says nothing about whether the source has been read since."""
        source = watch_build.source(name="fi.se news", check_frequency=CheckFrequency.DAILY)
        now = timezone.now()
        swept_at = now - datetime.timedelta(days=3)
        watch_build.source_check(source, status=CheckStatus.OK, checked_at=swept_at)
        run = agent_build.platform_run(key=self.key)
        self.log_check(
            run,
            {
                "sourceName": source.name,
                "status": "ok",
                "kind": "recheck",
                "subjectType": SubjectType.OBLIGATION.value,
                "subjectId": str(uuid.uuid4()),
            },
        )
        row = self.coverage()[0]
        self.assertTrue(row["overdue"], "the last sweep is still three days old")
        self.assertEqual(row["lastStatus"], "ok")
        self.assertEqual(
            row["lastCheckedAt"][:10],
            swept_at.date().isoformat(),
            "the page shows the last sweep, not the last re-check",
        )

    def test_the_coverage_read_costs_the_same_however_many_sources_there_are(self) -> None:
        """NFR-02: correlated sub-selects, not a query per source. One source and five cost
        the same, which is the property that matters; the number itself is printed by the
        assertion when it moves."""
        watch_build.source(name="fi.se news")
        with self.assertNumQueries(2):
            sources_logic.source_coverage(["en"])
        for index in range(4):
            watch_build.source(name=f"another source {index}")
        with self.assertNumQueries(2):
            sources_logic.source_coverage(["en"])

    def test_an_empty_registry_answers_200_with_an_empty_list(self) -> None:
        self.assertEqual(self.coverage(), [])


class SourceCadence(TestCase):
    """The cadence table is what the words mean, so every kind the model allows has one."""

    def test_every_cadence_the_model_allows_has_a_span(self) -> None:
        self.assertEqual(sorted(sources_logic.CADENCE), sorted(kind.value for kind in CheckFrequency))


class StandardsPublishers(WatchSourceCase):
    """A standards publisher's pages are not read automatically until a lawyer has read its
    terms (WAT-07, D-45): a source of the `standards_body` kind, or one whose address is on
    a host in `STANDARDS_PUBLISHER_HOSTS`, is registered with its checks off, and a run may
    not log a check of a source whose checks are off."""

    def test_out_of_the_box_no_standards_publisher_is_read(self) -> None:
        """The default lists every publisher whose terms were read (D-45), and a source on
        any of them is registered with its checks off."""
        for host in settings.STANDARDS_PUBLISHER_HOSTS:
            with self.subTest(host=host):
                response = self.register({**NEW_SOURCE, "name": host, "url": f"https://www.{host}/"})
                self.assertEqual(response.status_code, 201, response.content)
                self.assertFalse(response.json()["active"])
        self.assertTrue({"iso.org", "iec.ch"} <= set(settings.STANDARDS_PUBLISHER_HOSTS))

    @override_settings(STANDARDS_PUBLISHER_HOSTS=[])
    def test_an_ordinary_source_is_registered_with_its_checks_on(self) -> None:
        response = self.register({**NEW_SOURCE, "url": "https://www.iso.org/news.html"})
        self.assertTrue(response.json()["active"], "the list, not the address, holds a publisher back")

    def test_a_standards_body_source_is_registered_with_its_checks_off(self) -> None:
        response = self.register(
            {**NEW_SOURCE, "name": "ISO news", "url": "https://www.iso.org/news.html", "kind": "standards_body"}
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.json()["active"])
        event = AuditEvent.objects.get(action=sources_logic.REGISTERED)
        self.assertFalse(event.after["active"], "the audit row records the state it was registered in")

    @override_settings(STANDARDS_PUBLISHER_HOSTS=["iso.org", "iec.ch"])
    def test_a_source_on_a_publisher_host_is_registered_with_its_checks_off_whatever_its_kind(self) -> None:
        for name, url in (("ISO", "https://www.iso.org/news.html"), ("IEC", "https://iec.ch/news")):
            with self.subTest(url=url):
                response = self.register({**NEW_SOURCE, "name": name, "url": url})
                self.assertEqual(response.status_code, 201, response.content)
                self.assertFalse(response.json()["active"])

    @override_settings(STANDARDS_PUBLISHER_HOSTS=["iso.org"])
    def test_a_host_that_only_ends_like_a_publisher_is_not_one(self) -> None:
        response = self.register({**NEW_SOURCE, "url": "https://notiso.org/news"})
        self.assertTrue(response.json()["active"])

    @override_settings(STANDARDS_PUBLISHER_HOSTS=["iso.org"])
    def test_an_editor_cannot_switch_a_publishers_checks_on_or_move_a_source_onto_one(self) -> None:
        publisher = watch_build.source(name="ISO news", url="https://www.iso.org/news.html", active=False)
        ordinary = watch_build.source(name="fi.se news")
        for source, body in ((publisher, {"active": True}), (ordinary, {"url": "https://www.iso.org/news.html"})):
            with self.subTest(source=source.name), self.as_editor():
                response = self.client.patch(
                    f"{SOURCES}/{source.id}", data=body, content_type=JSON, **self.session_headers()
                )
            self.assertEqual(response.status_code, 422, response.content)
            self.assertEqual(response.json()["code"], "validation_error")
            source.refresh_from_db()
            self.assertIs(source.active, source is ordinary, "a refusal stores nothing")
        self.assertEqual(ordinary.url, "https://www.fi.se/", "nor moves the address")

    def test_a_run_may_not_log_a_check_of_a_source_whose_checks_are_off(self) -> None:
        source = watch_build.source(name="ISO news", active=False)
        run = agent_build.platform_run(key=self.key)
        for body in (
            {"sourceName": source.name, "status": "ok", "itemsFound": 1},
            {"sourceName": source.name, "status": "failed", "error": "403 from the publisher"},
        ):
            with self.subTest(status=body["status"]):
                response = self.log_check(run, body)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "source_inactive")
        self.assertEqual(source.checks.count(), 0, "a refusal logs nothing")
        self.assertFalse(AuditEvent.objects.filter(action=sources_logic.CHECK_LOGGED).exists())
