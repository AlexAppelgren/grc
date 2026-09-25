"""Tagging a record with the bank's own tags (VOC-08): one by one, or in a previewed batch.

Four routes under `vocab.manage`, each taking the subject in the body: `POST /taggings`,
`POST /taggings/remove`, `POST /taggings/preview` and `POST /taggings/batch`. These pin
the rule branches VOC-S12 does not walk: every subject kind, the three refusals, the
idempotent repeats, the records a caller may not read (skipped, counted and never named)
and the cap.

Proven to fail 2026-09-25 in a scratch copy: with the readability filter dropped, the
other bank's case was tagged in this bank's zone and counted as gained; with the cap check
removed, a batch of three passed a cap of two.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import Client, TestCase, override_settings

from apps.cases import testing as cases_build
from apps.identity.models import TenantRole
from apps.library import testing as library_build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent
from apps.shared.testing import sign_in
from apps.taxonomy.models import Tagging, TenantTag, TenantTagLabel
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from apps.watch import testing as watch_build

V1 = "/api/v1"


class TaggingTests(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        watch_build.seed_watch_reference()
        self.tenant = factories.tenant(slug="tagging-bank")
        self.other = factories.tenant(slug="tagging-other")
        for company in (self.tenant, self.other):
            tenancy.activate(company.id)
            ensure_tenant_vocabularies(company, actor=Actor.system("test"))
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        self.reader = factories.member(self.tenant, roles=("reader",)).user
        self.custody = self._tag(self.tenant, "custody", "Custody")
        self.instrument = library_build.instrument(key="tagging-lvm", regime="regime:securities")
        self.obligations = [library_build.obligation(self.instrument, key=f"obl-tagging-{n}") for n in range(3)]
        self.change = watch_build.change(title="FI amends the custody rules")
        self.case = cases_build.case(self.tenant, self.change)
        self.foreign_case = cases_build.case(self.other, watch_build.change(title="Another bank's change"))
        self.private = library_build.obligation(self.instrument, key="obl-tagging-private", owner_tenant=self.other)
        tenancy.activate(self.tenant.id)

    def _tag(self, company: Any, key: str, label: str) -> TenantTag:
        tenancy.activate(company.id)
        row = TenantTag.objects.create(tenant=company, key=key)
        TenantTagLabel.objects.create(tenant=company, vocabulary=row, language="en", text=label, is_original=True)
        return row

    def _post(self, path: str, body: dict[str, Any], user: Any = None) -> Any:
        headers = sign_in(user or self.officer, tenant=self.tenant) if user is not False else {}
        response = Client().post(f"{V1}{path}", data=body, content_type="application/json", **headers)
        tenancy.activate(self.tenant.id)
        return response

    def _one(self, path: str, subject_type: str, subject_id: Any, tag: str = "custody", user: Any = None) -> Any:
        return self._post(path, {"tagKey": tag, "subjectType": subject_type, "subjectId": str(subject_id)}, user)

    def _batch(self, path: str, ids: list[Any], subject_type: str = "obligation", tag: str = "custody") -> Any:
        return self._post(path, {"tagKey": tag, "subjectType": subject_type, "subjectIds": [str(i) for i in ids]})

    def _events(self) -> Any:
        """Tagging's own audit rows: signing in writes session rows of its own."""
        return AuditEvent.objects.filter(action__startswith="taggings.")

    def _tagged(self, subject_id: Any) -> list[str]:
        return list(Tagging.objects.filter(subject_id=subject_id).values_list("tag__key", flat=True))

    # --- one record -------------------------------------------------------------------------
    def test_every_subject_kind_is_tagged_and_audited_with_its_title(self) -> None:
        subjects = [
            ("obligation", self.obligations[0].id, "obl-tagging-0"),
            ("change", self.change.id, "FI amends the custody rules"),
            ("change_case", self.case.id, "FI amends the custody rules"),
        ]
        for subject_type, subject_id, title in subjects:
            with self.subTest(kind=subject_type):
                response = self._one("/taggings", subject_type, subject_id)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["tags"], [{"key": "custody", "kind": None, "label": "Custody"}])
                self.assertEqual((response.json()["subjectType"], response.json()["subjectId"]), (subject_type, str(subject_id)))
                self.assertEqual(self._tagged(subject_id), ["custody"])
                event = AuditEvent.objects.filter(action="taggings.added", subject_id=subject_id).get()
                self.assertEqual((event.subject_type, event.subject_title, event.after["tag"]), (subject_type, title, "custody"))

    def test_a_repeated_add_and_a_repeated_remove_change_nothing(self) -> None:
        obligation = self.obligations[0]
        for _ in range(2):
            self.assertEqual(self._one("/taggings", "obligation", obligation.id).status_code, 200)
        self.assertEqual(Tagging.objects.filter(subject_id=obligation.id).count(), 1)
        added = AuditEvent.objects.filter(action="taggings.added", subject_id=obligation.id)
        self.assertEqual(sorted(event.after["changed"] for event in added), [False, True])
        for _ in range(2):
            response = self._one("/taggings/remove", "obligation", obligation.id)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["tags"], [])
        removed = AuditEvent.objects.filter(action="taggings.removed", subject_id=obligation.id)
        self.assertEqual(sorted(event.after["changed"] for event in removed), [False, True])
        self.assertEqual(self._tagged(obligation.id), [])

    def test_a_retired_tag_is_not_applied_but_still_comes_off(self) -> None:
        obligation = self.obligations[0]
        Tagging.objects.create(tenant=self.tenant, tag=self.custody, subject_type="obligation", subject_id=obligation.id)
        TenantTag.objects.filter(pk=self.custody.pk).update(active=False)
        refused = self._one("/taggings", "obligation", self.obligations[1].id)
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"))
        self.assertEqual(self._one("/taggings/remove", "obligation", obligation.id).status_code, 200)
        self.assertEqual(self._tagged(obligation.id), [])

    def test_refusals_name_their_code_and_write_nothing(self) -> None:
        cases = [
            ("tenant_obligation", self.obligations[0].id, "custody", 422, "unsupported_subject"),
            ("instrument", self.instrument.id, "custody", 422, "unsupported_subject"),
            ("obligation", self.obligations[0].id, "no_such_tag", 422, "unknown_key"),
            ("change_case", self.foreign_case.id, "custody", 404, "not_found"),
            ("obligation", self.private.id, "custody", 404, "not_found"),
            ("obligation", uuid.uuid4(), "custody", 404, "not_found"),
        ]
        for subject_type, subject_id, tag, status, code in cases:
            for path in ("/taggings", "/taggings/remove"):
                with self.subTest(kind=subject_type, tag=tag, path=path):
                    response = self._one(path, subject_type, subject_id, tag=tag)
                    self.assertEqual((response.status_code, response.json()["code"]), (status, code))
        self.assertFalse(self._events().exists())
        self.assertFalse(Tagging.objects.exists())

    def test_another_banks_tag_is_an_unknown_key(self) -> None:
        self._tag(self.other, "theirs", "Theirs")
        tenancy.activate(self.tenant.id)
        response = self._one("/taggings", "obligation", self.obligations[0].id, tag="theirs")
        self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_key"))

    def test_only_vocab_manage_tags_and_only_a_session_calls(self) -> None:
        one = {"tagKey": "custody", "subjectType": "obligation", "subjectId": str(self.obligations[0].id)}
        many = {"tagKey": "custody", "subjectType": "obligation", "subjectIds": [str(self.obligations[0].id)]}
        for path, body in (("/taggings", one), ("/taggings/remove", one), ("/taggings/preview", many), ("/taggings/batch", many)):
            with self.subTest(path=path):
                denied = self._post(path, body, self.reader)
                self.assertEqual(denied.status_code, 403, denied.content)
                self.assertEqual(denied.json()["requiredPermission"], "vocab.manage")
                self.assertEqual(self._post(path, body, False).status_code, 401)
        self.assertFalse(Tagging.objects.exists())

    def test_the_subject_never_rides_in_the_request_line(self) -> None:
        refused = Client().post(
            f"{V1}/taggings?tagKey=custody&subjectType=obligation&subjectId={self.obligations[0].id}",
            **sign_in(self.officer, tenant=self.tenant),
        )
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertFalse(Tagging.objects.exists())

    # --- a batch ----------------------------------------------------------------------------
    def test_the_preview_counts_what_would_happen_and_writes_nothing(self) -> None:
        first, second, third = self.obligations
        Tagging.objects.create(tenant=self.tenant, tag=self.custody, subject_type="obligation", subject_id=first.id)
        missing = uuid.uuid4()
        response = self._batch("/taggings/preview", [first.id, second.id, third.id, self.private.id, missing, second.id])
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["tag"], {"key": "custody", "kind": None, "label": "Custody"})
        self.assertEqual(body["subjectType"], "obligation")
        self.assertEqual((body["gained"]["count"], set(body["gained"]["ids"])), (2, {str(second.id), str(third.id)}))
        self.assertEqual((body["alreadyTagged"]["count"], body["alreadyTagged"]["ids"]), (1, [str(first.id)]))
        self.assertEqual(body["skipped"], {"count": 2})
        # A record the caller cannot read is never named, anywhere in the answer.
        self.assertNotIn(str(self.private.id), response.content.decode())
        self.assertNotIn(str(missing), response.content.decode())
        self.assertFalse(self._events().exists())
        self.assertEqual(Tagging.objects.count(), 1)

    def test_a_batch_writes_one_event_with_the_key_and_the_ids(self) -> None:
        first, second, third = self.obligations
        Tagging.objects.create(tenant=self.tenant, tag=self.custody, subject_type="obligation", subject_id=first.id)
        response = self._batch("/taggings/batch", [first.id, second.id, third.id, self.private.id])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["gained"]["count"], 2)
        self.assertEqual(response.json()["skipped"], {"count": 1})
        events = list(self._events())
        self.assertEqual([event.action for event in events], ["taggings.batch_added"])
        event = events[0]
        self.assertEqual((event.subject_type, event.subject_id, event.after["tag"]), ("tenant_tag", self.custody.id, "custody"))
        self.assertEqual(set(event.after["ids"]), {str(first.id), str(second.id), str(third.id)})
        self.assertEqual(set(event.after["added"]), {str(second.id), str(third.id)})
        self.assertEqual(event.after["skipped"], 1)
        self.assertNotIn(str(self.private.id), str(event.after))
        self.assertEqual(sorted(self._tagged(o.id) for o in self.obligations), [["custody"]] * 3)
        self.assertEqual(self._tagged(self.private.id), [])
        # Again: idempotent, and one event saying nothing changed.
        again_before = [event.id for event in events]
        again = self._batch("/taggings/batch", [first.id, second.id, third.id])
        self.assertEqual((again.json()["gained"]["count"], again.json()["alreadyTagged"]["count"]), (0, 3))
        repeat = list(self._events().exclude(id__in=again_before))
        self.assertEqual([(e.action, e.after["added"]) for e in repeat], [("taggings.batch_added", [])])
        self.assertEqual(Tagging.objects.filter(tag=self.custody).count(), 3)

    def test_the_other_banks_case_is_skipped_and_stays_untagged(self) -> None:
        response = self._batch("/taggings/batch", [self.case.id, self.foreign_case.id], subject_type="change_case")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["gained"]["ids"], response.json()["skipped"]), ([str(self.case.id)], {"count": 1}))
        tenancy.activate(self.other.id)
        self.assertFalse(Tagging.objects.exists())

    def test_a_kind_the_caller_may_not_read_is_skipped_whole(self) -> None:
        """A role holding vocab.manage but not cases.read reads no case, so tags none."""
        TenantRole.objects.create(tenant=self.tenant, key="tagger", permissions=["vocab.manage", "library.read"])
        tagger = factories.member(self.tenant, roles=("tagger",)).user
        tenancy.activate(self.tenant.id)
        body = {"tagKey": "custody", "subjectType": "change_case", "subjectIds": [str(self.case.id)]}
        response = self._post("/taggings/batch", body, tagger)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["gained"]["count"], response.json()["skipped"]), (0, {"count": 1}))
        single = self._one("/taggings", "change_case", self.case.id, user=tagger)
        self.assertEqual((single.status_code, single.json()["code"]), (404, "not_found"))
        self.assertFalse(Tagging.objects.exists())

    def test_a_batch_names_one_kind_and_a_known_tag(self) -> None:
        for path in ("/taggings/preview", "/taggings/batch"):
            with self.subTest(path=path):
                kind = self._batch(path, [self.obligations[0].id], subject_type="tenant_obligation")
                self.assertEqual((kind.status_code, kind.json()["code"]), (422, "unsupported_subject"))
                tag = self._batch(path, [self.obligations[0].id], tag="no_such_tag")
                self.assertEqual((tag.status_code, tag.json()["code"]), (422, "unknown_key"))
                empty = self._batch(path, [])
                self.assertEqual(empty.status_code, 422, empty.content)
        self.assertFalse(Tagging.objects.exists())

    @override_settings(BULK_TAGGING_MAX_RECORDS=2)
    def test_a_batch_above_the_cap_is_refused_whole(self) -> None:
        ids = [o.id for o in self.obligations]
        for path in ("/taggings/preview", "/taggings/batch"):
            with self.subTest(path=path):
                response = self._batch(path, ids)
                self.assertEqual((response.status_code, response.json()["code"]), (422, "too_many_records"))
        # The cap counts distinct records, so a repeated id does not push a batch over it.
        self.assertEqual(self._batch("/taggings/batch", [ids[0], ids[1], ids[0]]).status_code, 200)
        self.assertEqual(Tagging.objects.count(), 2)
