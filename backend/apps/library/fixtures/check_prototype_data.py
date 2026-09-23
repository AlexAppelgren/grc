#!/usr/bin/env python
"""Referential integrity check for prototype_data.json (chunk 3 seeds load this file).

Every reference in the fixture must resolve: instruments to authorities, regimes (a term
of the `regime` dimension, required on every instrument, D-39) and jurisdictions;
obligations to instruments; terms to taxonomy terms; changes to authorities and
obligations; proposals to targets, changes and runs; sources to authorities; audit rows to
their subjects; tenant rows to users and obligations; every vocabulary key used to the
`vocabularies` section; every date to ISO 8601. Every obligation carries a verified date
and every version a summary in its original language, no provision sits under an
instrument whose level's kind is `standard` (D-35: a standard's text is licensed), and
`_meta.anchor_date` (an instrument's verified date when nothing else gives one) is a
date. With `--eval` it also checks that backend/eval/retrieval.jsonl and
classification.jsonl only name keys that exist here, so the evaluation sets cannot drift
from the corpus.

Exit 0 when clean, 1 with every problem listed. No Django, no database: plain Python.

    python backend/apps/library/fixtures/check_prototype_data.py [--eval]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "prototype_data.json"
EVAL_DIR = HERE.parents[2] / "eval"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class Checker:
    def __init__(self, data: dict) -> None:
        self.d = data
        self.problems: list[str] = []
        v = data["vocabularies"]
        self.vocab: dict[str, set[str]] = {name: set(rows) for name, rows in v.items()}
        self.terms = {f"{t['dimension']}:{t['key']}" for t in data["taxonomy_terms"]}
        self.regimes = {f"{t['dimension']}:{t['key']}" for t in data["taxonomy_terms"] if t["dimension"] == "regime"}
        self.standard_levels = {key for key, row in v["instrument_level"].items() if row.get("kind") == "standard"}
        self.tags = {t["key"] for t in data["tags"]}
        self.jurisdictions = {j["code"] for j in data["jurisdictions"]}
        self.authorities = {a["key"] for a in data["authorities"]}
        self.instruments = {i["stable_key"] for i in data["instruments"]}
        self.provisions = {p["stable_key"] for p in data["provisions"]}
        self.obligations = {o["stable_key"] for o in data["obligations"]}
        self.changes = {c["stable_key"] for c in data["regulatory_changes"]}
        self.proposals = {p["stable_key"] for p in data["proposals"]}
        self.sources = {s["key"] for s in data["sources"]}
        self.users = {u["id"] for u in data["users"]}
        self.runs = {r["key"] for r in data["agent_runs"]}
        self.agents = {a["agent"] for a in data["tenant_agents"]}
        self.entities = {e["key"] for e in data["tenant"]["legal_entities"]}
        self.tenants = {data["tenant"]["key"]}
        self.kinds = {name: set(values) for name, values in data["_meta"]["kinds_used"].items()}

    # -- helpers ---------------------------------------------------------------------
    def problem(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def ref(self, where: str, value: object, universe: set[str], what: str, optional: bool = False) -> None:
        if value is None:
            if not optional:
                self.problem(where, f"{what} is required")
            return
        if value not in universe:
            self.problem(where, f"{what} {value!r} does not exist")

    def refs(self, where: str, values: object, universe: set[str], what: str) -> None:
        if not isinstance(values, list):
            self.problem(where, f"{what} must be a list")
            return
        for value in values:
            self.ref(where, value, universe, what)

    def vocab_key(self, where: str, vocabulary: str, value: object, optional: bool = False) -> None:
        self.ref(where, value, self.vocab[vocabulary], f"{vocabulary} key", optional)

    def kind(self, where: str, kind: str, value: object, optional: bool = False) -> None:
        self.ref(where, value, self.kinds[kind], f"{kind} kind", optional)

    def date(self, where: str, value: object, optional: bool = True) -> None:
        if value is None:
            if not optional:
                self.problem(where, "date is required")
            return
        if not isinstance(value, str) or not DATE_RE.match(value):
            self.problem(where, f"{value!r} is not an ISO date")
            return
        try:
            date.fromisoformat(value)
        except ValueError:
            self.problem(where, f"{value!r} is not a real date")

    def datetime(self, where: str, value: object, optional: bool = True) -> None:
        if value is None:
            if not optional:
                self.problem(where, "timestamp is required")
            return
        if not isinstance(value, str) or not DATETIME_RE.match(value):
            self.problem(where, f"{value!r} is not an ISO timestamp")
            return
        try:
            datetime.fromisoformat(value)
        except ValueError:
            self.problem(where, f"{value!r} is not a real timestamp")

    def unique(self, rows: list[dict], field: str, table: str) -> None:
        seen: set[str] = set()
        for row in rows:
            value = row[field]
            if value in seen:
                self.problem(table, f"duplicate {field} {value!r}")
            seen.add(value)

    # -- tables ----------------------------------------------------------------------
    def run(self) -> list[str]:
        d = self.d
        self.date("_meta.anchor_date", d["_meta"]["anchor_date"], optional=False)
        for name, rows in d["vocabularies"].items():
            for key, row in rows.items():
                where = f"vocabularies.{name}.{key}"
                for field in ("label_en", "label_sv", "usage_note"):
                    if not row.get(field):
                        self.problem(where, f"{field} missing")
        for t in d["taxonomy_terms"]:
            self.vocab_key(f"taxonomy_terms.{t['key']}", "term_dimension", t["dimension"])
        dims_keys = [f"{t['dimension']}:{t['key']}" for t in d["taxonomy_terms"]]
        if len(dims_keys) != len(set(dims_keys)):
            self.problem("taxonomy_terms", "duplicate dimension:key")
        for a in d["authorities"]:
            self.ref(f"authorities.{a['key']}", a["jurisdiction"], self.jurisdictions, "jurisdiction")
        for j in d["jurisdictions"]:
            self.ref(f"jurisdictions.{j['code']}", j["parent_code"], self.jurisdictions, "parent_code", optional=True)

        self.unique(d["instruments"], "stable_key", "instruments")
        for i in d["instruments"]:
            where = f"instruments.{i['stable_key']}"
            if i["regime"] is None:
                self.problem(where, "regime is required")
            elif i["regime"] not in self.regimes:
                self.problem(where, f"regime {i['regime']!r} is not a term of the regime dimension")
            self.vocab_key(where, "instrument_level", i["level"])
            self.ref(where, i["authority"], self.authorities, "authority", optional=True)
            self.ref(where, i["jurisdiction"], self.jurisdictions, "jurisdiction")
            self.ref(where, i["verified_by"], self.users, "verified_by", optional=True)
            self.kind(where, "record_status", i["status"])
            self.date(where + ".in_force_from", i["in_force_from"])
            # A precision is optional (the loader defaults to a day) and goes with its date.
            self.kind(where, "date_precision", i.get("in_force_from_precision"), optional=True)
            if i.get("in_force_from_precision") and i["in_force_from"] is None:
                self.problem(where, "in_force_from_precision needs in_force_from")
            self.date(where + ".in_force_to", i["in_force_to"])
            self.date(where + ".last_verified_at", i["last_verified_at"])
            if not i["source_url"]:
                self.problem(where, "source_url is required")
        for r in d["instrument_relations"]:
            where = f"instrument_relations.{r['from_instrument']}->{r['to_instrument']}"
            self.ref(where, r["from_instrument"], self.instruments, "from_instrument")
            self.ref(where, r["to_instrument"], self.instruments, "to_instrument")
            self.vocab_key(where, "relation_type", r["relation"])
            if r["from_instrument"] == r["to_instrument"]:
                self.problem(where, "relates an instrument to itself")
        self.unique(d["provisions"], "stable_key", "provisions")
        standards = {i["stable_key"] for i in d["instruments"] if i["level"] in self.standard_levels}
        for p in d["provisions"]:
            where = f"provisions.{p['stable_key']}"
            self.ref(where, p["instrument"], self.instruments, "instrument")
            if p["instrument"] in standards:
                self.problem(where, "a standard's text is licensed, so no provision sits under one")
            self.ref(where, p["parent"], self.provisions, "parent", optional=True)
        for op in d["obligation_provisions"]:
            where = f"obligation_provisions.{op['obligation']}"
            self.ref(where, op["obligation"], self.obligations, "obligation")
            self.ref(where, op["provision"], self.provisions, "provision")
        provision_versions_per: dict[str, set[int]] = {}
        for v in d.get("provision_versions", []):
            where = f"provision_versions.{v['provision']}#{v['version_no']}"
            self.ref(where, v["provision"], self.provisions, "provision")
            self.date(where + ".effective_from", v["effective_from"])
            if not v["text_en"] or not v["text_sv"]:
                self.problem(where, "text_en and text_sv are required")
            if not v.get(f"text_{v['original_language']}"):
                self.problem(where, f"no text in its original language {v['original_language']!r}")
            if v["version_no"] in provision_versions_per.setdefault(v["provision"], set()):
                self.problem(where, "duplicate version_no")
            provision_versions_per[v["provision"]].add(v["version_no"])

        self.unique(d["obligations"], "stable_key", "obligations")
        for o in d["obligations"]:
            where = f"obligations.{o['stable_key']}"
            self.ref(where, o["instrument"], self.instruments, "instrument")
            self.vocab_key(where, "duty_type", o["duty_type"])
            self.refs(where, o["tags"], self.tags, "tag")
            self.kind(where, "origin_type", o["created_origin"])
            self.ref(where, o["created_by_agent_run"], self.runs, "created_by_agent_run", optional=True)
            self.ref(where, o["verified_by"], self.users, "verified_by", optional=True)
            self.date(where + ".last_verified_at", o["last_verified_at"], optional=False)
            if not o["title"] or not o["ref_label"]:
                self.problem(where, "title and ref_label are required")
        versions_per: dict[str, set[int]] = {}
        for v in d["obligation_versions"]:
            where = f"obligation_versions.{v['obligation']}#{v['version_no']}"
            self.ref(where, v["obligation"], self.obligations, "obligation")
            self.ref(where, v["change"], self.changes, "change", optional=True)
            self.ref(where, v["proposal"], self.proposals, "proposal", optional=True)
            self.ref(where, v["approved_by"], self.users, "approved_by", optional=True)
            self.date(where + ".effective_from", v["effective_from"])
            self.date(where + ".effective_to", v["effective_to"])
            if not v["summary_en"] or not v["summary_sv"]:
                self.problem(where, "summary_en and summary_sv are required")
            if not v.get(f"summary_{v['original_language']}"):
                self.problem(where, f"no summary in its original language {v['original_language']!r}")
            if v["version_no"] in versions_per.setdefault(v["obligation"], set()):
                self.problem(where, "duplicate version_no")
            versions_per[v["obligation"]].add(v["version_no"])
        for key in self.obligations - set(versions_per):
            self.problem(f"obligations.{key}", "has no version")
        seen_terms: set[tuple[str, str]] = set()
        for t in d["obligation_terms"]:
            where = f"obligation_terms.{t['obligation']}"
            self.ref(where, t["obligation"], self.obligations, "obligation")
            self.ref(where, t["term"], self.terms, "term")
            if (t["obligation"], t["term"]) in seen_terms:
                self.problem(where, f"duplicate term {t['term']}")
            seen_terms.add((t["obligation"], t["term"]))
        for r in d["obligation_relations"]:
            where = f"obligation_relations.{r['obligation']}->{r['related_obligation']}"
            self.ref(where, r["obligation"], self.obligations, "obligation")
            self.ref(where, r["related_obligation"], self.obligations, "related_obligation")
            self.vocab_key(where, "relation_type", r["relation"])
            if r["obligation"] == r["related_obligation"]:
                self.problem(where, "relates an obligation to itself")

        self.unique(d["regulatory_changes"], "stable_key", "regulatory_changes")
        for c in d["regulatory_changes"]:
            where = f"regulatory_changes.{c['stable_key']}"
            self.vocab_key(where, "change_type", c["change_type"])
            self.ref(where, c["authority"], self.authorities, "authority", optional=True)
            self.vocab_key(where, "urgency", c["suggested_urgency"], optional=True)
            self.refs(where, c["flags"], self.vocab["flag"], "flag")
            self.kind(where, "origin_type", c["origin"])
            self.kind(where, "change_status", c["status"])
            self.ref(where, c["agent_run"], self.runs, "agent_run", optional=True)
            self.date(where + ".published_on", c["published_on"])
            self.date(where + ".key_date", c["key_date"])
            self.kind(where, "date_precision", c["published_precision"], optional=True)
            self.kind(where, "date_precision", c["key_date_precision"], optional=True)
            if (c["published_on"] is None) != (c["published_precision"] is None):
                self.problem(where, "published_on and published_precision go together")
            if (c["key_date"] is None) != (c["key_date_precision"] is None):
                self.problem(where, "key_date and key_date_precision go together")
            for field in ("title", "summary", "authority_label", "source_label", "source_url"):
                if not c[field]:
                    self.problem(where, f"{field} is required")
        for e in d["change_events"]:
            where = f"change_events.{e['change']}#{e['sort_order']}"
            self.ref(where, e["change"], self.changes, "change")
            self.date(where, e["event_date"])
            self.kind(where, "date_precision", e["date_precision"], optional=True)
            if (e["event_date"] is None) != (e["date_precision"] is None):
                self.problem(where, "event_date and date_precision go together")
        seen_docs: set[tuple[str, str]] = set()
        primaries: dict[str, int] = {}
        for doc in d["change_documents"]:
            where = f"change_documents.{doc['change']}"
            self.ref(where, doc["change"], self.changes, "change")
            if (doc["change"], doc["url"]) in seen_docs:
                self.problem(where, f"duplicate url {doc['url']}")
            seen_docs.add((doc["change"], doc["url"]))
            if doc["is_primary"]:
                primaries[doc["change"]] = primaries.get(doc["change"], 0) + 1
        for key in self.changes:
            if primaries.get(key, 0) != 1:
                self.problem(f"regulatory_changes.{key}", "needs exactly one primary document")
        for t in d["change_terms"]:
            where = f"change_terms.{t['change']}"
            self.ref(where, t["change"], self.changes, "change")
            self.ref(where, t["term"], self.terms, "term")
        for link in d["change_obligations"]:
            where = f"change_obligations.{link['change']}->{link['obligation']}"
            self.ref(where, link["change"], self.changes, "change")
            self.ref(where, link["obligation"], self.obligations, "obligation")
            self.kind(where, "origin_type", link["origin"])
            self.ref(where, link["confirmed_by"], self.users, "confirmed_by", optional=True)

        self.unique(d["proposals"], "stable_key", "proposals")
        for p in d["proposals"]:
            where = f"proposals.{p['stable_key']}"
            self.kind(where, "proposal_kind", p["kind"])
            self.kind(where, "proposal_status", p["status"])
            self.kind(where, "origin_type", p["origin"])
            self.ref(where, p["change"], self.changes, "change", optional=True)
            self.ref(where, p["agent_run"], self.runs, "agent_run", optional=True)
            self.date(where + ".effective_from", p["effective_from"])
            if p["target_type"] == "obligation":
                self.ref(where, p["target"], self.obligations, "target obligation")
            elif p["target_type"] is not None:
                self.problem(where, f"unknown target_type {p['target_type']!r}")
            payload = p["payload"]
            if "instrument" in payload:
                self.ref(where + ".payload", payload["instrument"], self.instruments, "instrument")
            if "terms" in payload:
                self.refs(where + ".payload", payload["terms"], self.terms, "term")
            if "duty_type" in payload:
                self.vocab_key(where + ".payload", "duty_type", payload["duty_type"])

        self.unique(d["sources"], "key", "sources")
        self.unique(d["sources"], "name", "sources")
        for s in d["sources"]:
            where = f"sources.{s['key']}"
            self.vocab_key(where, "source_kind", s["kind"])
            self.ref(where, s["authority"], self.authorities, "authority", optional=True)
            self.ref(where, s["owner_tenant"], self.tenants, "owner_tenant", optional=True)
        for c in d["source_checks"]:
            where = f"source_checks.{c['source']}"
            self.ref(where, c["source"], self.sources, "source")
            self.ref(where, c["agent_run"], self.runs, "agent_run", optional=True)
            self.kind(where, "check_status", c["status"])
            self.datetime(where, c["checked_at"], optional=False)

        subject_universe = {"change_case": self.changes, "change": self.changes, "proposal": self.proposals, "obligation": self.obligations}
        for i, a in enumerate(d["audit_events"]):
            where = f"audit_events[{i}]"
            self.kind(where, "actor_type", a["actor_type"])
            self.datetime(where, a["occurred_at"], optional=False)
            self.ref(where, a["tenant"], self.tenants, "tenant", optional=True)
            if a["actor_type"] == "user":
                self.ref(where, a["actor_user"], self.users, "actor_user")
            else:
                self.ref(where, a["actor_agent"], self.agents, "actor_agent")
            if a["subject_type"] not in subject_universe:
                self.problem(where, f"unknown subject_type {a['subject_type']!r}")
            else:
                self.ref(where, a["subject"], subject_universe[a["subject_type"]], "subject")

        for u in d["users"]:
            self.ref(f"users.{u['id']}", u["tenant"], self.tenants, "tenant")
        for e in d["tenant"]["legal_entities"]:
            self.ref(f"tenant.legal_entities.{e['key']}", e["kind"], self.terms, "kind term")
        for p in d["tenant"]["products"]:
            where = f"tenant.products.{p['key']}"
            self.ref(where, p["legal_entity"], self.entities, "legal_entity")
            self.ref(where, p["owner"], self.users, "owner")
            self.refs(where, p["terms"], self.terms, "term")
        for f in d["footprint_terms"]:
            self.ref("footprint_terms", f["term"], self.terms, "term")
            self.ref("footprint_terms", f["added_by"], self.users, "added_by")
        for t in d["tenant_obligations"]:
            where = f"tenant_obligations.{t['obligation']}"
            self.ref(where, t["obligation"], self.obligations, "obligation")
            self.kind(where, "applicability", t["applicability"])
            self.vocab_key(where, "compliance_status", t["compliance_status"])
            self.vocab_key(where, "risk_rating", t["risk_rating"])
            self.ref(where, t["first_line_owner"], self.users, "first_line_owner")
            self.ref(where, t["compliance_contact"], self.users, "compliance_contact")
            self.date(where + ".next_review_date", t["next_review_date"])
        for link in d["internal_links"]:
            where = f"internal_links.{link['obligation']}"
            self.ref(where, link["obligation"], self.obligations, "obligation")
            self.vocab_key(where, "link_kind", link["link_kind"])
        for c in d["change_cases"]:
            where = f"change_cases.{c['change']}"
            self.ref(where, c["change"], self.changes, "change")
            self.kind(where, "case_status", c["status"])
            self.vocab_key(where, "urgency", c["urgency"])
            self.ref(where, c["owner"], self.users, "owner", optional=True)
            self.ref(where, c["signed_by"], self.users, "signed_by", optional=True)
            self.date(where + ".closed_at", c["closed_at"])
        for a in d["impact_assessments"]:
            where = f"impact_assessments.{a['change']}"
            self.ref(where, a["change"], self.changes, "change")
            self.kind(where, "assessment_applies", a["applies"])
            self.kind(where, "effort_size", a["effort"])
            self.date(where + ".internal_deadline", a["internal_deadline"])
        for a in d["actions"]:
            where = f"actions.{a['prototype_id']}"
            self.ref(where, a["change"], self.changes, "change")
            self.ref(where, a["owner"], self.users, "owner")
            self.date(where, a["due_on"], optional=False)
        for e in d["evidence"]:
            self.ref("evidence", e["change"], self.changes, "change")
            self.kind("evidence", "evidence_kind", e["kind"])
        for g in d["gaps"]:
            where = f"gaps.{g['key']}"
            self.ref(where, g["obligation"], self.obligations, "obligation")
            self.kind(where, "gap_status", g["status"])
            self.kind(where, "gap_source", g["source"])
            self.ref(where, g["owner"], self.users, "owner")
            self.ref(where, g["raised_by"], self.users, "raised_by")
            self.date(where + ".target_date", g["target_date"])
            for a in g["actions"]:
                self.ref(where + ".actions", a["owner"], self.users, "owner")
                self.date(where + ".actions", a["due_on"], optional=False)
        self.unique(d["agent_runs"], "key", "agent_runs")
        for r in d["agent_runs"]:
            where = f"agent_runs.{r['key']}"
            self.ref(where, r["agent"], self.agents, "agent")
            self.kind(where, "run_status", r["status"])
            self.datetime(where, r["started_at"], optional=False)
        return self.problems

    # -- evaluation sets -------------------------------------------------------------
    def check_eval_sets(self) -> None:
        corpus = self.obligations | self.provisions | self.changes
        for row in read_jsonl(EVAL_DIR / "retrieval.jsonl"):
            where = f"retrieval.jsonl {row.get('id')}"
            self.refs(where, row.get("expected"), corpus, "expected key")
            self.date(where + ".as_of", row.get("as_of"))
            if "predictions" in row:
                self.refs(where, row["predictions"], corpus, "prediction")
        for row in read_jsonl(EVAL_DIR / "classification.jsonl"):
            where = f"classification.jsonl {row.get('id')}"
            expected = row.get("expected", {})
            self.vocab_key(where, "change_type", expected.get("change_type"), optional=bool(row.get("injection")))
            self.refs(where, expected.get("flags", []), self.vocab["flag"], "flag")
            for dimension, keys in expected.get("scope", {}).items():
                self.vocab_key(where, "term_dimension", dimension)
                self.refs(where, [f"{dimension}:{k}" for k in keys], self.terms, "scope term")


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def main(argv: list[str]) -> int:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    checker = Checker(data)
    problems = checker.run()
    if "--eval" in argv:
        checker.check_eval_sets()
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    print("prototype_data: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if problems:
        for p in problems:
            print("  " + p)
        print(f"prototype_data: FAILED, {len(problems)} problem(s)")
        return 1
    print("prototype_data: ok" + (" (evaluation sets cross-checked)" if "--eval" in argv else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
