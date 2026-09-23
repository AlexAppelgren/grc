#!/usr/bin/env python
"""The published API explains itself (docs/plans/briefs/API_DOCUMENTATION.md).

The reader we write for is an integrator at a bank who has never seen this codebase and
cannot ask us a question. `openapi.json` is the whole manual, so this gate judges the
exported contract and never the Python source: a `Field(description=...)` that does not
reach the contract has documented nothing, and a docstring the generator drops cannot be
allowed to pass the gate.

Four rules, one per kind of thing a reader needs (the standard's sections 1 to 4):

  description   Every property of every request and response schema carries a description
                of at least one sentence that says what the fact is in the bank's
                language. A description that only re-spaces the property name ("Effective
                From" for `effectiveFrom`) says nothing and fails.
  values        Every fixed value set is spelled out in words: an `enum` names each of its
                members, and a string property whose values are vocabulary rows names the
                vocabulary and says an admin may extend it. A vocabulary is never
                presented as a closed enum.
  limits        Every `maxLength`, `maximum`, `minimum`, `format` and `default` in the
                schema is also stated in words, because a reader reads the sentence and
                not the keyword.
  operations    Every operation carries a summary in the user's voice (Ninja titles one
                from its function name, so a summary that only re-spaces its operationId
                fails the same way a property name does), a description and at least one
                example, and every RFC 9457 `code` it documents is one a route can raise.

Vocabulary-backed strings are found two ways, never by guessing from a name: by the
`key`/`kind` shape (a schema carrying both properties is a vocabulary row, so a reference
to it and its own `key` are vocabulary-backed), and by VOCABULARY_PROPERTIES below, the
short explicit list of bare-string properties that hold a vocabulary key. Name-matching
was rejected: `stableKey`, `plainKey` and `requireResidentKey` all end in "key" and none
of them is a vocabulary row.

`backend/scripts/api_docs_pending.txt` holds what is not documented yet, one line per
schema class or operationId. The gate fails on anything undocumented that is not in the
ledger, and on a ledger line that is already documented, so the ledger can only shrink.
`--write-pending` regenerates it from the contract, keeping the app and reason already
recorded against a line. `--app <name>` is what a sweep runs: it ignores that app's ledger
lines and reports exactly what the app still owes, changing no file, so parallel sweeps
never edit the shared ledger to see their own work.

Proven to fail 2026-09-20 against the contract of the day (1173 findings over 263 schemas
and operations): with the ledger emptied (exit 1, all 263 named, each with the rule it
breaks and a compliant example), and with a line for the already-documented `Empty` left
in the ledger (exit 1, the stale line named), then restored.
apps/shared/tests_api_docs.py pins each rule against a worked example.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
BUILT = ROOT / "openapi.json"
PENDING = BACKEND / "scripts" / "api_docs_pending.txt"
METHODS = ("get", "post", "put", "patch", "delete")

# A description has to be a sentence about the fact, not a label. Twenty-five characters is
# the shortest real one we could write ("The tenant's own case id." is 25), so anything
# under it is a label with a full stop.
MIN_DESCRIPTION = 25

# An RFC 9457 code is snake_case with at least one underscore (`four_eyes_violation`,
# `stale_write`). Requiring the underscore is what keeps the bare words a description uses
# about errors -- `code`, `status`, `detail` -- from being read as codes.
CODE_TOKEN = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")

# Every `code` a route can raise. apps/shared/errors.py is the contract's vocabulary: its
# STATUS_BY_CODE table plus the codes config/api.py raises for a request no route sees.
# A code a route can actually raise, read from the source rather than typed here. The
# hand-written list this replaces held 26 codes while `apps/` raised far more, so a sweep
# documenting `invalid_slug` or `idempotency_conflict` — codes the API really answers —
# failed the gate for telling the truth, and the honest way out was to leave the
# integrator without the value to branch on (first sweep, 2026-09-20). A test module is
# not a source: a code only a test names is a code no route raises.
CODE_LITERAL = re.compile(r"""code\s*=\s*["']([a-z][a-z0-9_]*)["']""")
# The exception handlers answer for requests no route sees, so their codes are read too:
# `enrolment_only` is the 403 an enrolment session gets from every route but passkey
# registration and `GET /me` (AC-ID2), and a caller has to be able to branch on it.
HANDLER_SOURCES = (BACKEND / "config" / "api.py",)
# Below this, the scan found nothing rather than the truth: fail closed.
CODES_FLOOR = 40


def raisable_codes() -> frozenset[str]:
    """Every `code=` literal under `backend/apps/`, outside its tests, and in the exception
    handlers of `config/api.py`."""
    found: set[str] = set()
    for path in [*(BACKEND / "apps").rglob("*.py"), *HANDLER_SOURCES]:
        name = path.name
        if name.startswith("tests_") or "/migrations/" in path.as_posix():
            continue
        found.update(CODE_LITERAL.findall(path.read_text(encoding="utf-8")))
    if len(found) < CODES_FLOOR:
        raise SystemExit(
            f"api_docs_gate: only {len(found)} error codes found under backend/apps, below the floor of "
            f"{CODES_FLOOR}. The scan is broken, not the contract; fix it rather than lowering the floor."
        )
    return frozenset(found)


RAISABLE_CODES = raisable_codes()

# Bare-string properties whose value set is a vocabulary an admin manages, where the
# `key`/`kind` shape is not visible in the contract. Short on purpose: a sweep adds the
# property it documents, and only after reading the model behind it.
VOCABULARY_PROPERTIES = frozenset(
    {
        "JurisdictionRow.parentKey",
        "MarketWatchBody.jurisdiction",
        "ObligationQuery.dutyType",
        "ObligationQuery.term",
        "TaxonomyTermRow.parentKey",
        "VocabularyCreateBody.kind",
        "VocabularyCreateBody.key",
    }
)

# A `format` is stated in words by its own name or by the plain English a reader expects,
# so a description can say "a UTC timestamp" instead of reciting "date-time".
FORMAT_WORDS = {
    "date-time": ("date-time", "datetime", "timestamp", "iso 8601"),
    "date": ("date",),
    "uuid": ("uuid", "identifier"),
    "uri": ("uri", "url", "link"),
    "email": ("email",),
}

# A tag names the app that owns the operation, and so the app that will close a ledger line.
APP_BY_TAG = {
    "Agents": "agents",
    "Billing": "billing",
    "Cases": "cases",
    "Collab": "collab",
    "Governance": "governance",
    "Home": "home",
    "Identity": "identity",
    "Integrations": "integrations",
    "Library": "library",
    "Proposals": "proposals",
    "Register": "register",
    "Reports": "reports",
    "Search": "search",
    "Shared": "shared",
    "Taxonomy": "taxonomy",
    "Tenants": "tenants",
    "Watch": "watch",
}

# What a compliant property looks like, printed with the finding so the fix needs no other
# file open. One line per rule, keyed by the rule the finding broke.
EXAMPLE_BY_RULE = {
    "description": (
        'effectiveFrom: Field(description="The date this rule starts binding the bank. '
        'A library fact, changed only through an approved proposal.")'
    ),
    "values": (
        'status: Field(description="Where the run stands: `running` while the agent works, '
        "`succeeded` when it filed its findings, `failed` when it stopped early and filed "
        'none.")'
    ),
    "limits": (
        'question: Field(max_length=2000, description="The question, at most 2000 '
        'characters; a longer one is refused with `validation_error`.")'
    ),
    "operations": (
        'router.get(..., summary="List the bank\'s agent keys", '
        'description="...", openapi_extra={"responses": {...examples...}})'
    ),
}


@dataclass(frozen=True)
class Finding:
    owner: str  # the schema class or operationId that must close it
    where: str  # Schema.property, or the operationId
    rule: str  # description | values | limits | operations
    what: str  # what is missing, in words

    def __str__(self) -> str:
        return f"  [{self.rule}] {self.where}: {self.what}"


def normalised(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def spaced_name(name: str) -> str:
    """`effectiveFrom` -> `effective from`: what a generator writes into `title` when
    nobody wrote a description. A description equal to this restates the name."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()


def resolve(schema: dict, schemas: dict) -> dict:
    seen: set[str] = set()
    while "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        if name in seen:
            return {}
        seen.add(name)
        schema = schemas.get(name, {})
    return schema


def branches(schema: dict) -> list[dict]:
    """A property and every branch of its `anyOf`/`oneOf`/`allOf`, and an array's items.
    Ninja writes an optional string as `anyOf: [string, null]`, so the enum, the format and
    the length sit on a branch rather than on the property itself."""
    found = [schema]
    for key in ("anyOf", "oneOf", "allOf"):
        for part in schema.get(key, []):
            found.extend(branches(part))
    if isinstance(schema.get("items"), dict):
        found.extend(branches(schema["items"]))
    return found


def enum_members(schema: dict) -> list[str]:
    members: list[str] = []
    for branch in branches(schema):
        for member in branch.get("enum", []):
            if isinstance(member, str) and member not in members:
                members.append(member)
    return members


def is_vocabulary_row(schema: dict) -> bool:
    """A vocabulary row is the `key`/`kind` shape: the stable key an API compares on and the
    kind that says which list it belongs to."""
    properties = schema.get("properties") or {}
    return "key" in properties and "kind" in properties


def vocabulary_backed(name: str, schema: dict, schemas: dict, owner_is_row: bool) -> bool:
    """The `key`/`kind` shape, the half the contract shows. The other half, bare strings
    that hold a vocabulary key, is VOCABULARY_PROPERTIES and is checked by the caller."""
    for branch in branches(schema):
        if "$ref" in branch and is_vocabulary_row(resolve(branch, schemas)):
            return True
    return owner_is_row and name == "key"


def stated_limits(schema: dict) -> list[tuple[str, object]]:
    """The keywords a reader must find restated in words, gathered across the branches."""
    found: list[tuple[str, object]] = []
    for branch in branches(schema):
        for keyword in ("maxLength", "maximum", "minimum", "format", "default"):
            if keyword in branch and (keyword, branch[keyword]) not in found:
                found.append((keyword, branch[keyword]))
    return found


def limit_is_stated(keyword: str, value: object, description: str) -> bool:
    """`maxLength: 2000` is stated by the digits 2000 appearing in the sentence, `format:
    uuid` by the word or a plain-English synonym for it, a boolean `default` by the word it
    means, since nobody writes "False" in a sentence.

    A number is matched as a substring, not on a word boundary, so "at most 100" also
    satisfies `minimum: 1`. Deliberately lenient: the finding worth having is a limit the
    description never mentions at all, and a stricter rule would make a writer pad a
    sentence with "at least 1" to please a gate nobody would thank."""
    text = description.lower()
    if isinstance(value, bool):
        return ("true" if value else "false") in text or ("on" if value else "off") in text
    if isinstance(value, (int, float)):
        return str(value) in text
    if keyword == "format" and isinstance(value, str):
        return any(word in text for word in FORMAT_WORDS.get(value, (value,)))
    if isinstance(value, str):
        return value.lower() in text or normalised(value) in normalised(text)
    return keyword.lower() in text


def check_property(schema_name: str, name: str, schema: dict, schemas: dict, owner_is_row: bool) -> list[Finding]:
    where = f"{schema_name}.{name}"
    description = (schema.get("description") or "").strip()
    if not description:
        return [Finding(schema_name, where, "description", "no description; every property needs one")]

    findings: list[Finding] = []
    restates = normalised(description) == normalised(spaced_name(name))
    if restates or len(description) < MIN_DESCRIPTION:
        fault = (
            "the description only restates the property name"
            if restates
            else f"the description is shorter than a sentence ({len(description)} characters, {MIN_DESCRIPTION} minimum)"
        )
        findings.append(
            Finding(
                schema_name,
                where,
                "description",
                f"{fault}; say what the fact is in the bank's language, where it comes from "
                f'(the library, the bank\'s own zone, an agent, the server) and what a reader '
                f'must not conclude from it (seen: "{description}")',
            )
        )

    members = enum_members(schema)
    missing = [member for member in members if f"`{member}`" not in description and member not in description]
    if missing:
        gap = (
            f"names none of the {len(members)} values the schema allows, {members}"
            if missing == members
            else f"never mentions {missing} of the values the schema allows, {members}"
        )
        findings.append(
            Finding(
                schema_name,
                where,
                "values",
                f"the description {gap}; give every value and what it means to the business",
            )
        )

    explicit = where in VOCABULARY_PROPERTIES
    if not members and (explicit or vocabulary_backed(name, schema, schemas, owner_is_row)):
        text = description.lower()
        if "vocabular" not in text or not ("admin" in text and ("extend" in text or "add" in text)):
            findings.append(
                Finding(
                    schema_name,
                    where,
                    "values",
                    "the values are vocabulary rows, so name the vocabulary and its kinds, say an "
                    "admin may extend them, and point at the vocabulary endpoint for the live set; "
                    "never present it as a closed enum",
                )
            )

    for keyword, value in stated_limits(schema):
        if not limit_is_stated(keyword, value, description):
            findings.append(
                Finding(
                    schema_name,
                    where,
                    "limits",
                    f"the schema says {keyword}={value!r} but the description never states it; "
                    f"a reader reads the sentence, not the keyword",
                )
            )
    return findings


def documented_codes(operation: dict) -> set[str]:
    """The RFC 9457 codes an operation tells a caller to branch on: backticked snake_case in
    the operation's description or in the description of any error response it documents."""
    text = operation.get("description") or ""
    for status, response in (operation.get("responses") or {}).items():
        if not str(status).startswith("2"):
            text += "\n" + (response.get("description") or "")
    return set(CODE_TOKEN.findall(text))


def has_nothing_to_show(operation: dict) -> bool:
    """True when the call carries no body in either direction, so there is no example to give.

    A `204` answers with no content by definition. Demanding an example of one pushed the
    first operation that met the rule into declaring `content: application/json` on a 204
    and typing its body as `unknown` in the generated client, which is the gate bending the
    API rather than describing it (`markVisit`, 2026-09-20). The description still has to
    say what the call changes; there is simply nothing to exemplify."""
    if operation.get("requestBody"):
        return False
    successes = [str(code) for code in (operation.get("responses") or {}) if str(code).startswith("2")]
    return bool(successes) and all(code == "204" for code in successes)


def has_example(operation: dict, schemas: dict) -> bool:
    """An example on the request body or on a 2xx response, written either beside the media
    type (`example`/`examples`) or on the schema the response points at."""
    media: list[dict] = []
    body = operation.get("requestBody") or {}
    media.extend((body.get("content") or {}).values())
    for status, response in (operation.get("responses") or {}).items():
        if str(status).startswith("2"):
            media.extend((response.get("content") or {}).values())
    for entry in media:
        if entry.get("example") is not None or entry.get("examples"):
            return True
        schema = resolve(entry.get("schema") or {}, schemas)
        if schema.get("example") is not None or schema.get("examples"):
            return True
    return False


def check_parameters(operation_id: str, operation: dict, schemas: dict) -> list[Finding]:
    """Ninja inlines a Query model into `parameters` and never references the component
    schema, so the pagination limits an integrator actually reads live here. A parameter
    carries its description either beside itself or on its schema; both count."""
    findings: list[Finding] = []
    for parameter in operation.get("parameters") or []:
        schema = dict(parameter.get("schema") or {})
        description = (parameter.get("description") or schema.get("description") or "").strip()
        schema["description"] = description
        findings.extend(check_property(operation_id, parameter.get("name", "?"), schema, schemas, False))
    return findings


def check_operation(operation_id: str, operation: dict, schemas: dict) -> list[Finding]:
    findings: list[Finding] = check_parameters(operation_id, operation, schemas)
    summary = (operation.get("summary") or "").strip()

    def fails(what: str) -> None:
        findings.append(Finding(operation_id, operation_id, "operations", what))

    if not summary:
        fails("no summary; say what the caller achieves")
    elif normalised(summary) == normalised(operation_id):
        # Ninja titles an operation from its function name, so "List Agent Keys" appears
        # written when nobody wrote it. Same trick as the property rule: a summary that only
        # re-spaces its own operationId tells the reader what they already read.
        fails(
            f'the summary only re-spaces the operationId (seen: "{summary}"); '
            f"say what the caller achieves, in the user's voice"
        )
    if not (operation.get("description") or "").strip():
        fails(
            "no description; say when to call it, what it changes, which permission or scope it "
            "needs and what it records in the audit"
        )
    if not has_nothing_to_show(operation) and not has_example(operation, schemas):
        fails(
            "no example on the request body or on any 2xx response; give one taken from the "
            "prototype's data, never from a real bank"
        )
    for code in sorted(documented_codes(operation) - RAISABLE_CODES):
        fails(
            f"documents the error code `{code}`, which no route under backend/apps raises; document a code "
            f"the API can actually answer, or stop documenting it"
        )
    return findings


def operations(document: dict) -> dict[str, tuple[dict, str]]:
    """operationId -> (operation, owning app)."""
    found: dict[str, tuple[dict, str]] = {}
    for item in document.get("paths", {}).values():
        for method in METHODS:
            operation = item.get(method)
            if not operation:
                continue
            tag = (operation.get("tags") or [""])[0]
            found[operation.get("operationId", "")] = (operation, APP_BY_TAG.get(tag, "unknown"))
    found.pop("", None)
    return found


def collect(document: dict) -> tuple[list[Finding], dict[str, str]]:
    """Every finding in the contract, and the app that owns each schema or operation."""
    schemas = document.get("components", {}).get("schemas", {})
    findings: list[Finding] = []
    app_by_owner: dict[str, str] = {}

    for operation_id, (operation, app) in sorted(operations(document).items()):
        app_by_owner[operation_id] = app
        findings.extend(check_operation(operation_id, operation, schemas))

    # A schema belongs to the app of the first operation that reaches it, so a ledger line
    # names the sweep that will close it.
    for _operation_id, (operation, app) in sorted(operations(document).items()):
        for name in sorted(referenced(operation, schemas)):
            app_by_owner.setdefault(name, app)

    for schema_name, schema in sorted(schemas.items()):
        owner_is_row = is_vocabulary_row(schema)
        for name, property_schema in sorted((schema.get("properties") or {}).items()):
            findings.extend(check_property(schema_name, name, property_schema, schemas, owner_is_row))
        app_by_owner.setdefault(schema_name, app_of_query_model(schema, document))
    return findings, app_by_owner


def app_of_query_model(schema: dict, document: dict) -> str:
    """A Ninja Query model is inlined into `parameters`, so no `$ref` reaches it and it
    inherits no app from an operation. Claim it for an app only when the evidence is
    exact: every one of its properties is a parameter of that app's operations, and of no
    other app's. `PageQuery` is shared by every app and stays "unknown" on purpose."""
    properties = set(schema.get("properties") or {})
    if not properties:
        return "unknown"
    apps = {
        app
        for operation, app in operations(document).values()
        if properties <= {parameter.get("name") for parameter in operation.get("parameters") or []}
    }
    return apps.pop() if len(apps) == 1 else "unknown"


def referenced(node: object, schemas: dict, seen: set[str] | None = None) -> set[str]:
    """Every component schema reachable from an operation, so a schema inherits its app."""
    seen = set() if seen is None else seen
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.split("/")[-1]
            if name not in seen:
                seen.add(name)
                referenced(schemas.get(name, {}), schemas, seen)
        for value in node.values():
            referenced(value, schemas, seen)
    elif isinstance(node, list):
        for value in node:
            referenced(value, schemas, seen)
    return seen


def pending_entries() -> dict[str, str]:
    """owner -> the rest of its line (app and reason), as recorded by a person."""
    entries: dict[str, str] = {}
    if not PENDING.exists():
        return entries
    for line in PENDING.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(?:schema|operation)\s+(?P<owner>\S+)\s+(?P<rest>.*)$", line)
        if not match:
            print(f"api_docs_gate: unparseable pending line: {line}")
            continue
        entries[match.group("owner")] = match.group("rest")
    return entries


def write_pending(findings: list[Finding], app_by_owner: dict[str, str], document: dict) -> int:
    existing = pending_entries()
    operation_ids = set(operations(document))
    by_owner: dict[str, list[Finding]] = {}
    for finding in findings:
        by_owner.setdefault(finding.owner, []).append(finding)

    lines = [
        "# What the published API does not explain yet, against the standard in",
        "# docs/plans/briefs/API_DOCUMENTATION.md. One line per schema class or operationId:",
        "#   schema|operation <name> app <app> <reason>",
        "#",
        "# THIS FILE MUST BE EMPTY BEFORE R1 IS CALLED DONE. It is the list of places where an",
        "# integrator at a bank still has to guess, and every one of them is a support call.",
        "#",
        "# A line is deleted when its schema or operation is documented to the standard; the gate",
        "# fails on a line that is already documented, so the ledger can only shrink. Generated by",
        "# scripts/api_docs_gate.py --write-pending, which keeps the app and reason already here.",
        "#",
        "# Sweeping one app: `python backend/scripts/api_docs_gate.py --app <app>` ignores that",
        "# app's lines and reports exactly what it still owes, touching no file. When it goes",
        "# green, delete that app's lines here and commit them with the descriptions.",
        "#",
        '# "app unknown" is a schema no operation references (a Ninja Query model inlined into',
        "# parameters, shared by every app); the sweep that documents it names its app.",
        "",
    ]
    header = len(lines)
    for owner in sorted(by_owner, key=lambda name: (name not in operation_ids, name)):
        kind = "operation" if owner in operation_ids else "schema"
        if owner in existing:
            lines.append(f"{kind} {owner} {existing[owner]}")
            continue
        app = app_by_owner.get(owner, "unknown")
        rules = sorted({finding.rule for finding in by_owner[owner]})
        count = len(by_owner[owner])
        reason = f"{count} finding{'s' if count != 1 else ''} ({', '.join(rules)})"
        lines.append(f"{kind} {owner} app {app} {reason}")
    PENDING.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"api_docs_gate: wrote {PENDING.relative_to(ROOT).as_posix()} ({len(lines) - header} entries)")
    return 0


def report(findings: list[Finding], pending: dict[str, str], *, report_stale: bool = True) -> int:
    by_owner: dict[str, list[Finding]] = {}
    for finding in findings:
        by_owner.setdefault(finding.owner, []).append(finding)

    unexplained = {owner: found for owner, found in by_owner.items() if owner not in pending}
    # Under --app the remaining ledger lines all belong to other apps, and one sweep is never
    # asked to close another's bookkeeping -- reporting them would only invite it to delete
    # a line it has not looked at.
    stale = sorted(owner for owner in pending if owner not in by_owner) if report_stale else []

    print(
        f"api_docs_gate: {len(findings)} finding(s) over {len(by_owner)} schema(s)/operation(s), "
        f"{len(pending)} in the ledger, {len(unexplained)} outside it, {len(stale)} stale"
    )
    rules_hit: set[str] = set()
    for owner in sorted(unexplained):
        print(f"{owner}:")
        for finding in unexplained[owner]:
            print(str(finding))
            rules_hit.add(finding.rule)
    for owner in stale:
        print(f"  stale ledger line (already documented): {owner}")
    if rules_hit:
        print("\nWhat a documented one looks like:")
        for rule in sorted(rules_hit):
            print(f"  {rule}: {EXAMPLE_BY_RULE[rule]}")
    if unexplained or stale:
        print(
            "\nThe standard is docs/plans/briefs/API_DOCUMENTATION.md. Document it in the app's "
            "schemas.py or api.py, regenerate with `bash generate-types.sh`, then delete its line "
            "from backend/scripts/api_docs_pending.txt."
        )
        print("Reproduce: python backend/scripts/api_docs_gate.py")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-pending", action="store_true", help="regenerate the ledger from the contract")
    parser.add_argument(
        "--app",
        help="check one app: its ledger lines are ignored, so the gate reports exactly what that "
        "app still owes and goes green when it owes nothing. Changes no file; delete the lines "
        "for real once it is green.",
    )
    args = parser.parse_args(argv)
    if not BUILT.exists():
        print(f"api_docs_gate: {BUILT} missing; run `bash generate-types.sh` first")
        return 1
    document = json.loads(BUILT.read_text(encoding="utf-8"))
    findings, app_by_owner = collect(document)
    if args.write_pending:
        return write_pending(findings, app_by_owner, document)
    pending = pending_entries()
    if args.app:
        pending = {owner: rest for owner, rest in pending.items() if not rest.startswith(f"app {args.app} ")}
        return report(findings, pending, report_stale=False)
    return report(findings, pending)


if __name__ == "__main__":
    sys.exit(main())
