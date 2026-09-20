"""Scenario stubs for the shared app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Several of these are already proven by the structural guards in this app
(tests_rls.py, tests_production_guard.py, tests_route_permissions.py,
tests_health.py, ...). The stubs stay until each scenario is un-skipped
against the guard that proves it, so the coverage gate reads one source.

Prefixes hosted: NFR (S1..S16), I18N (S3, S4 are @e2e only, no stub).

Operations exercised (the audit-on-write guard reads these names): createProposal.
"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest import skip

from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.models import Proposal
from apps.shared import factories
from apps.shared.audit import Actor
from apps.shared import permissions as perms
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import TaxonomyTerm, Urgency
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from config.api import api

V1 = "/api/v1"
WRITE_METHODS = frozenset({"POST", "PATCH", "PUT"})
# A field that would let a person choose how a pill looks (NFR-03): the tone follows the
# slot or the row's kind, never a choice.
CHOSEN_TONE_FIELDS = ("tone", "colour", "color")
# A response property named like presentation: the API sends keys, kinds and counts, and the
# client derives the pill and the phrase (playbook 15). Matched per camelCase word, so
# `milestone` is not a tone.
PRESENTATION_WORD = re.compile(r"(tone|colou?r|pill|badge|phrase)s?")
# A vocabulary reference inside a record carries exactly these. A term's key is unique only
# within its dimension, so a term reference may also carry that dimension's key.
VOCABULARY_REFERENCE = frozenset({"key", "kind", "label"})
LIST_KEY_FIELDS = frozenset({"dimension"})


def presentation_problems(openapi: dict[str, Any]) -> list[str]:
    """Walk every response schema of an OpenAPI document and name each property that
    carries presentation, and each vocabulary reference that is not exactly {key, kind,
    label}. A record is a response's root, a root list's element or a page's `items`; an
    object nested in a record that has a `key` and a `label` references a vocabulary row."""
    components = openapi["components"]["schemas"]
    problems: set[str] = set()
    seen: set[tuple[str, bool]] = set()

    def walk(schema: dict[str, Any], where: str, record: bool) -> None:
        ref = schema.get("$ref")
        if ref is not None:
            name = ref.rsplit("/", 1)[-1]
            if (name, record) not in seen:
                seen.add((name, record))
                walk(components[name], name, record)
            return
        for combined in ("allOf", "anyOf", "oneOf"):
            for part in schema.get(combined, []):
                walk(part, where, record)
        if isinstance(schema.get("items"), dict):
            walk(schema["items"], f"{where}[]", record)
        if isinstance(schema.get("additionalProperties"), dict):
            walk(schema["additionalProperties"], f"{where}{{}}", False)
        properties = schema.get("properties", {})
        fields = set(properties)
        if not record and {"key", "label"} <= fields:
            if not VOCABULARY_REFERENCE <= fields or not fields - VOCABULARY_REFERENCE <= LIST_KEY_FIELDS:
                problems.add(f"{where} is a vocabulary reference with {sorted(fields)}, not key, kind and label")
        for name, child in properties.items():
            if any(PRESENTATION_WORD.fullmatch(word.lower()) for word in re.findall(r"[A-Za-z][a-z0-9]*", name)):
                problems.add(f"{where}.{name} names presentation; send a key, a kind or a count")
            walk(child, f"{where}.{name}", record=record and name == "items" and child.get("type") == "array")

    for path, item in openapi["paths"].items():
        for method, operation in item.items():
            for code, response in operation.get("responses", {}).items():
                for content in response.get("content", {}).values():
                    if "schema" in content:
                        walk(content["schema"], f"{method.upper()} {path} {code}", record=True)
    return sorted(problems)


def names_field(error: dict[str, str], name: str) -> bool:
    """A 422 names the refused field: the field itself, or `extra` with the key in its message."""
    field = error["field"].rsplit(".", 1)[-1]
    return field == name or (field == "extra" and name in error["message"])


class SharedScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.shared, one method per @integration scenario."""

    @skip("pending: NFR-S1")
    def test_nfr_s1(self) -> None:
        """NFR-S1

        A record of tenant A requested by tenant B answers 404 on every tenant route.
        """

    @skip("pending: NFR-S2")
    def test_nfr_s2(self) -> None:
        """NFR-S2

        The app refuses to boot on a role that can bypass row-level security.
        """

    @skip("pending: NFR-S3")
    def test_nfr_s3(self) -> None:
        """NFR-S3

        Every tenant table has row-level security enabled, forced and with a policy.
        """

    @skip("pending: NFR-S4")
    def test_nfr_s4(self) -> None:
        """NFR-S4

        An unset tenant matches no rows.
        """

    @skip("pending: NFR-S5")
    def test_nfr_s5(self) -> None:
        """NFR-S5

        Every tenant task is wrapped in @tenant_task and every beat entry exists.
        """

    @skip("pending: NFR-S6")
    def test_nfr_s6(self) -> None:
        """NFR-S6

        Every API response carries Server-Timing and the budget is enforced.
        """

    def test_nfr_s10(self) -> None:
        """NFR-S10

        Tone is never chosen by a person and the API never sends a phrase.
        """
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenant = factories.tenant(slug="bank")
        self.activate(tenant)
        ensure_tenant_vocabularies(tenant, actor=Actor.system("test"))
        # vocab.manage for the tenant's lists, proposals.create for the library's.
        session = sign_in(factories.member(tenant, roles=("admin", "compliance_officer")).user, tenant=tenant)
        openapi = api.get_openapi_schema(path_prefix=V1)
        schemas = openapi["components"]["schemas"]

        # Every vocabulary and term write refuses a tone or a colour, at the top of its body
        # and inside `extra`, on a tenant list (risk_rating) and a library list (urgency).
        urgency = Urgency.objects.order_by("sort_order", "key").values_list("key", flat=True).first()
        term_id = str(TaxonomyTerm.objects.order_by("key").values_list("id", flat=True).first())
        slots = (
            {"{list_name}": "risk_rating", "{key}": "low", "{term_id}": term_id},
            {"{list_name}": "urgency", "{key}": str(urgency), "{term_id}": term_id},
        )
        checked = 0
        for op in iter_operations(api):
            if op.method not in WRITE_METHODS or not op.path.startswith(("/vocab/", "/taxonomy/terms")):
                continue
            operation = openapi["paths"][f"{V1}{op.path}"][op.method.lower()]
            if "requestBody" not in operation:
                continue  # takes no body, so no field can name a tone
            body = schemas[operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]]
            payloads: list[tuple[dict[str, Any], str]] = [({name: "negative"}, name) for name in CHOSEN_TONE_FIELDS]
            if "extra" in body["properties"]:
                payloads += [({"extra": {name: "negative"}}, name) for name in CHOSEN_TONE_FIELDS]
            paths = []
            for slot in slots:
                path = op.path
                for placeholder, value in slot.items():
                    path = path.replace(placeholder, value)
                paths += [path] if path not in paths else []
            for path in paths:
                for payload, name in payloads:
                    with self.subTest(operation=op.operation_id, path=path, payload=payload):
                        response = self.client.generic(
                            op.method, f"{V1}{path}", json.dumps(payload), content_type="application/json", **session
                        )
                        self.assertEqual(response.status_code, 422, response.content)
                        problem = response.json()
                        self.assertEqual(problem["code"], "validation_error")
                        self.assertTrue(any(names_field(error, name) for error in problem["errors"]), problem)
                        checked += 1
        self.assertGreaterEqual(checked, 50, "the enumeration of vocabulary writes is broken")

        # A proposal is refused when it is made, never when it is approved: from the platform
        # editor's session and from an agent's key with proposals:write alike.
        editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))
        agent = {"HTTP_X_API_KEY": factories.api_key(tenant, scopes=(perms.SCOPE_PROPOSALS_WRITE,)).plain_key}
        flag = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}
        for who, headers in (("editor", editor), ("agent", agent)):
            for payload in ({**flag, "tone": "positive"}, {**flag, "extra": {"colour": "green"}}):
                with self.subTest(who=who, payload=payload):
                    before = Proposal.objects.count()
                    proposal = {"kind": "vocabulary_create", "title": "Add Client money", "payload": payload}
                    response = self.client.post(f"{V1}/proposals", proposal, content_type="application/json", **headers)
                    self.assertEqual(response.status_code, 422, response.content)
                    self.assertEqual(response.json()["code"], "validation_error")
                    self.assertEqual(Proposal.objects.count(), before)
            # Without the tone the same proposal is made, so the refusal was the tone's.
            proposal = {"kind": "vocabulary_create", "title": f"Add Client money ({who})", "payload": flag}
            made = self.client.post(f"{V1}/proposals", proposal, content_type="application/json", **headers)
            self.assertEqual(made.status_code, 201, made.content)

        # No response carries a tone, a colour, a pill, a badge or a phrase, and every
        # vocabulary reference is key, kind and label.
        self.assertEqual(presentation_problems(openapi), [])
        # The walk finds what it is meant to find: a planted tone, reference and phrase.
        response_ref = {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Row"}}}}}
        planted = {
            "paths": {"/rows": {"get": {"responses": response_ref}}},
            "components": {
                "schemas": {
                    "Row": {"properties": {"pillTone": {"type": "string"}, "urgency": {"$ref": "#/components/schemas/Ref"}}},
                    "Ref": {"properties": {"key": {}, "label": {}, "phrase": {}}},
                }
            },
        }
        self.assertEqual(len(presentation_problems(planted)), 3, presentation_problems(planted))

    @skip("pending: NFR-S11")
    def test_nfr_s11(self) -> None:
        """NFR-S11

        An unrecognised environment name is treated as production.
        """

    @skip("pending: NFR-S12")
    def test_nfr_s12(self) -> None:
        """NFR-S12

        The boot guards refuse an unsafe deployed configuration.
        """

    @skip("pending: NFR-S13")
    def test_nfr_s13(self) -> None:
        """NFR-S13

        Every route is permission-gated or ungated by design with a reason.
        """

    @skip("pending: NFR-S14")
    def test_nfr_s14(self) -> None:
        """NFR-S14

        /health/ names the failing component.
        """

    @skip("pending: NFR-S15")
    def test_nfr_s15(self) -> None:
        """NFR-S15

        Tenant content and personal data beyond name and id never reach logs or Sentry.
        """

    @skip("pending: NFR-S16")
    def test_nfr_s16(self) -> None:
        """NFR-S16

        Every error uses one shape and an empty answer is 200.
        """
