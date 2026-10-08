"""The public registers' jobs (TEN-07, TEN-08; PUBLIC_REGISTERS.md 3.1, 3.4, 5.2).

A lookup is a job: `start_lookup` writes it and hands it to the worker once the request
commits; `run_lookup` finds the company in GLEIF, walks its children breadth first and reads
each company's facts from the register of its country, then stores what it found or fails
whole (`lookup_not_found`, `lookup_ambiguous`, `register_unavailable`), never with a partial
result. Nothing in the organisation changes until a person applies it: `apply_lookup` adds or
links the chosen companies through the organisation's own write path and stores their register
facts. It writes no licence row, and the scope then follows the organisation by itself, once
for all the companies (apps/taxonomy/organisation_scope.py, D-122).

`recheck` is the nightly re-read: for every register entry of an active legal entity it reads
the register again and stores what changed, with an audit event naming the change. It never
edits the organisation; what changed reaches the scope by itself the same way, and a register
that cannot be reached leaves the stored facts as they are.

The functions here write the bank's rows and name no library model; the register reads and the
mapping are apps/tenants/registers_logic.py's. Nothing here logs a number or a name: a skipped
re-read logs the entry's id.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.identity.models import User
from apps.reports.models import JobStatus
from apps.reports.schemas import JobStatusValue
from apps.shared.adapters.registers import LEI, REGISTRATION_NUMBER, LeiCompany, RegistersAdapter, RegisterUnavailable, digits, get_registers
from apps.shared.audit import Actor, batched, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy import organisation_scope
from apps.tenants import organisation, registers_logic
from apps.tenants.models import OrgUnit, OrgUnitKind, RegisterEntry, RegisterLookup
from apps.tenants.schemas import (
    LookupErrorValue,
    RegisterApplyOut,
    RegisterFacts,
    RegisterLookupCompany,
    RegisterLookupEntity,
    RegisterLookupOut,
    RegisterLookupResult,
    TenantOrgUnitBody,
)

logger = logging.getLogger(__name__)

LOOKUP = "register_lookup"
ENTRY = "register_entry"


# ---------------------------------------------------------------------------------------
# The lookup
# ---------------------------------------------------------------------------------------
def start_lookup(*, tenant: Tenant, actor: Actor, user: User, query: str) -> RegisterLookup:
    """`POST /tenant/register-lookups`: an LEI (upper-cased) or a registration number as typed,
    or 422 `invalid_query` before anything is written."""
    from apps.tenants import tasks  # the worker's module imports this one

    query = query.strip()
    if LEI.fullmatch(query.upper()):
        query = query.upper()
    elif not REGISTRATION_NUMBER.fullmatch(query):
        raise ValidationError(
            "Type an organisation number, such as 556000-0001, or a 20-character LEI.", code="invalid_query"
        )
    lookup = RegisterLookup.objects.create(tenant=tenant, query=query, requested_by=user)
    record(
        action="register_lookup.started",
        actor=actor,
        subject_type=LOOKUP,
        subject_id=lookup.id,
        subject_title=query,
        summary="Started a lookup in the public registers.",
        tenant_id=tenant.id,
        after={"query": query},
    )
    tenant_id, lookup_id = str(tenant.id), str(lookup.id)
    transaction.on_commit(lambda: tasks.run_register_lookup.delay(tenant_id, lookup_id))
    return lookup


def lookup_of(tenant: Tenant, lookup_id: uuid.UUID, *, lock: bool = False) -> RegisterLookup:
    """The lookup, in the caller's bank and under its row-level security, or 404."""
    rows = RegisterLookup.objects.select_for_update() if lock else RegisterLookup.objects
    lookup = rows.filter(tenant=tenant, pk=lookup_id).first()  # ordering: pk lookup, at most one row
    if lookup is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return lookup


def _clock() -> float:
    """The clock REGISTERS_JOB_SECONDS is measured on, so a test can move it."""
    return time.monotonic()


def _group(registers: RegistersAdapter, root: LeiCompany) -> list[LeiCompany]:
    """The company and the companies under it, breadth first, at most REGISTERS_MAX_ENTITIES."""
    companies = [root]
    seen = {root.lei}
    index = 0
    while index < len(companies) and len(companies) < settings.REGISTERS_MAX_ENTITIES:
        for child in registers.children(companies[index].lei):
            if child.lei not in seen and len(companies) < settings.REGISTERS_MAX_ENTITIES:
                seen.add(child.lei)
                companies.append(child)
        index += 1
    return companies


def _with_facts(registers: RegistersAdapter, company: LeiCompany, covered: dict[str, Any]) -> RegisterLookupCompany:
    """GLEIF's company with the facts of its country's register, where bleqq reads one."""
    if company.country not in covered:
        covered[company.country] = registers_logic.authority_for_country(company.country)
    authority = covered[company.country]
    read = None
    if authority is not None and REGISTRATION_NUMBER.fullmatch(company.registration_number):
        read = registers.licence_facts(authority.key, company.registration_number)
    return RegisterLookupCompany(
        lei=company.lei,
        name=company.name,
        registration_number=company.registration_number,
        country=company.country,
        parent_lei=company.parent_lei,
        lei_status=company.lei_status,
        authority=authority.key if authority is not None else None,
        facts=registers_logic.register_facts(authority.key, read) if read is not None else None,
        source_url=read.source_url if read is not None else None,
    )


def _finish(lookup: RegisterLookup, *, code: str, companies: list[RegisterLookupCompany]) -> None:
    lookup.status = JobStatus.FAILED.value if code else JobStatus.SUCCEEDED.value
    lookup.error = code
    lookup.result = RegisterLookupResult(entities=companies).model_dump(mode="json", by_alias=True)
    lookup.completed_at = timezone.now()
    lookup.save(update_fields=["status", "error", "result", "completed_at"])
    record(
        action="register_lookup.finished",
        actor=Actor.system("register lookup"),
        subject_type=LOOKUP,
        subject_id=lookup.id,
        subject_title=lookup.query,
        summary="A lookup in the public registers failed." if code else "A lookup in the public registers finished.",
        tenant_id=lookup.tenant_id,
        after={
            "status": lookup.status,
            "error": code or None,
            "companies": len(companies),
            "withFacts": sum(1 for company in companies if company.facts is not None),
        },
    )


def run_lookup(tenant_id: uuid.UUID, lookup_id: str) -> None:
    """The worker's half of a lookup, inside the bank's own transaction. Only a queued lookup
    runs, under a row lock, so a second delivery of the same message changes nothing."""
    lookup = RegisterLookup.objects.select_for_update().filter(pk=lookup_id, tenant_id=tenant_id).first()  # ordering: pk lookup, at most one row
    if lookup is None or lookup.status != JobStatus.QUEUED.value:
        return
    registers = get_registers()
    try:
        found = registers.find(lookup.query)
        if not found:
            _finish(lookup, code="lookup_not_found", companies=[])
            return
        if len(found) > 1:
            _finish(lookup, code="lookup_ambiguous", companies=[])
            return
        deadline = _clock() + settings.REGISTERS_JOB_SECONDS
        covered: dict[str, Any] = {}
        companies = []
        for company in _group(registers, found[0]):
            if _clock() > deadline:
                raise RegisterUnavailable("the registers took longer than REGISTERS_JOB_SECONDS")
            companies.append(_with_facts(registers, company, covered))
    except RegisterUnavailable:
        _finish(lookup, code="register_unavailable", companies=[])
        return
    _finish(lookup, code="", companies=companies)


def _result(lookup: RegisterLookup) -> RegisterLookupResult:
    return RegisterLookupResult.model_validate(lookup.result) if lookup.result else RegisterLookupResult(entities=[])


def _legal_entities(tenant: Tenant) -> list[OrgUnit]:
    return list(OrgUnit.objects.filter(tenant=tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, active=True).order_by("name", "id"))


def _match(units: list[OrgUnit], company: RegisterLookupCompany) -> OrgUnit | None:
    """The bank's active legal entity that is this company: the same LEI, else the same
    registration number (digits compared) in the same country or with no country recorded."""
    number = digits(company.registration_number)
    by_lei = next((unit for unit in units if unit.lei and unit.lei == company.lei), None)
    return by_lei or next(
        (unit for unit in units if number and digits(unit.org_number) == number and unit.country_code in ("", company.country)),
        None,
    )


def _entity_type(company: RegisterLookupCompany) -> str | None:
    if company.facts is None or company.authority is None:
        return None
    return registers_logic.entity_type(company.authority, company.facts)


def lookup_out(*, tenant: Tenant, lookup: RegisterLookup, order: list[str]) -> RegisterLookupOut:
    """The lookup as the routes answer it, with what the bank's organisation already says
    about each company computed now, so it is never stale against the organisation."""
    companies = _result(lookup).entities
    units = _legal_entities(tenant)
    types = {company.lei: _entity_type(company) for company in companies}
    refs = registers_logic.entity_terms({key for key in types.values() if key}, order)
    entities = []
    for company in companies:
        existing = _match(units, company)
        entity_key = types[company.lei]
        entities.append(
            RegisterLookupEntity(
                **company.model_dump(),
                existing_org_unit_id=existing.id if existing is not None else None,
                preselected=company.facts is not None,
                unmapped=registers_logic.unmapped(company.authority, company.facts) if company.facts and company.authority else [],
                entity_type=refs.get(entity_key) if entity_key else None,
            )
        )
    return RegisterLookupOut(
        id=lookup.id,
        query=lookup.query,
        status=cast(JobStatusValue, lookup.status),
        error=cast(LookupErrorValue | None, lookup.error or None),
        created_at=lookup.created_at,
        completed_at=lookup.completed_at,
        entities=entities,
    )


# ---------------------------------------------------------------------------------------
# Applying a lookup
# ---------------------------------------------------------------------------------------
def _placed_ancestor(company: RegisterLookupCompany, by_lei: dict[str, RegisterLookupCompany], placed: dict[str, uuid.UUID]) -> uuid.UUID | None:
    """The unit of the nearest company above this one that was chosen, if any."""
    parent, seen = company.parent_lei, set()
    while parent is not None and parent not in placed and parent in by_lei and parent not in seen:
        seen.add(parent)
        parent = by_lei[parent].parent_lei
    return placed.get(parent) if parent is not None else None


@batched()
def apply_lookup(*, tenant: Tenant, actor: Actor, order: list[str], lookup_id: uuid.UUID, leis: list[str]) -> RegisterApplyOut:
    """`POST /tenant/register-lookups/{lookupId}/apply`: every refusal comes before any write.
    The chosen companies are taken parents first; one the bank has is linked and left as it is,
    any other is added as a legal entity under the nearest chosen company above it, else under
    the bank's group, and each company with register facts gets them stored."""
    lookup = lookup_of(tenant, lookup_id, lock=True)
    if lookup.status != JobStatus.SUCCEEDED.value:
        raise ValidationError("This lookup has not finished. Wait until it has, then add the companies.", code="lookup_not_done")
    companies = _result(lookup).entities
    by_lei = {company.lei: company for company in companies}
    unknown = sorted(set(leis) - set(by_lei))
    if unknown:
        raise ValidationError(f"Not a company this lookup found: {', '.join(unknown[:5])}.", code="unknown_lei")
    wanted = set(leis)
    chosen = [company for company in companies if company.lei in wanted]
    units = _legal_entities(tenant)
    group = OrgUnit.objects.filter(tenant=tenant, kind=OrgUnitKind.GROUP.value, active=True).order_by("name", "id").first()
    refs = registers_logic.entity_terms({key for key in map(_entity_type, chosen) if key}, order)
    authorities = registers_logic.authorities({company.authority for company in chosen if company.authority})
    placed: dict[str, uuid.UUID] = {}
    created = 0
    for company in chosen:
        unit = _match(units, company)
        if unit is not None:
            placed[company.lei] = unit.id
        else:
            entity_key = _entity_type(company)
            body = TenantOrgUnitBody(
                kind="legal_entity",
                name=company.name,
                parent_id=_placed_ancestor(company, by_lei, placed) or (group.id if group is not None else None),
                org_number=company.registration_number,
                lei=company.lei,
                country_code=company.country,
                entity_term=entity_key if entity_key in refs else None,
            )
            placed[company.lei] = organisation.create_org_unit(tenant=tenant, actor=actor, order=order, body=body, follow=False).id
            created += 1
        authority = authorities.get(company.authority or "")
        if company.facts is not None and authority is not None and lookup.completed_at is not None:
            _store(tenant, actor, placed[company.lei], authority.id, company.facts, company.source_url or "", lookup.completed_at)
    record(
        action="register_lookup.applied",
        actor=actor,
        subject_type=LOOKUP,
        subject_id=lookup.id,
        subject_title=lookup.query,
        summary="Added the chosen companies from the public registers to the organisation.",
        tenant_id=tenant.id,
        after={"created": created, "linked": len(chosen) - created},
    )
    # Once for every company added, after their facts are stored (D-122).
    organisation_scope.follow(tenant=tenant)
    units_out = organisation.org_units_out(tenant, [placed[company.lei] for company in chosen], order)
    return RegisterApplyOut(created=created, linked=len(chosen) - created, org_units=units_out)


def _stored(facts: RegisterFacts) -> dict[str, Any]:
    return facts.model_dump(mode="json", by_alias=True)


def _store(tenant: Tenant, actor: Actor, unit_id: uuid.UUID, authority_id: uuid.UUID, facts: RegisterFacts, source_url: str, read_at: Any) -> None:
    """A company's facts from a lookup: stored the first time, changed when they differ from
    what is stored and are newer, left alone otherwise."""
    entry = (
        RegisterEntry.objects.select_for_update()
        .filter(tenant=tenant, org_unit_id=unit_id, authority_id=authority_id)
        .first()  # ordering: unique (org_unit, authority), at most one row
    )
    if entry is None:
        entry = RegisterEntry.objects.create(
            tenant=tenant,
            org_unit_id=unit_id,
            authority_id=authority_id,
            facts=_stored(facts),
            source_url=source_url,
            read_at=read_at,
            changed_at=read_at,
        )
        record(
            action="register_entry.created",
            actor=actor,
            subject_type=ENTRY,
            subject_id=entry.id,
            subject_title=facts.name,
            summary="Stored a company's facts from a public register.",
            tenant_id=tenant.id,
            after={"orgUnitId": str(unit_id), "licences": len(facts.licences), "branches": len(facts.branches), "listed": facts.listed},
        )
    elif entry.read_at < read_at and entry.facts != _stored(facts):
        _change(entry, facts, source_url, read_at, actor)


# ---------------------------------------------------------------------------------------
# The nightly re-read
# ---------------------------------------------------------------------------------------
def _added(before: list[str], after: list[str]) -> list[str]:
    return [item for item in dict.fromkeys(after) if item not in set(before)]


def _diff(old: RegisterFacts, new: RegisterFacts) -> dict[str, Any]:
    """What a read changed, as the audit event names it: licences, branches and businesses
    added and removed, by their wording and names."""
    pairs = {
        "licences": ([licence.text for licence in old.licences], [licence.text for licence in new.licences]),
        "branches": ([branch.name for branch in old.branches], [branch.name for branch in new.branches]),
        "businesses": ([old.main_business, *old.other_businesses], [new.main_business, *new.other_businesses]),
    }
    diff: dict[str, Any] = {}
    for name, (before, after) in pairs.items():
        diff[f"{name}Added"] = _added(before, after)
        diff[f"{name}Removed"] = _added(after, before)
    return diff


def _change(entry: RegisterEntry, facts: RegisterFacts, source_url: str, read_at: Any, actor: Actor) -> None:
    old = RegisterFacts.model_validate(entry.facts)
    entry.facts = _stored(facts)
    entry.source_url = source_url
    entry.read_at = entry.changed_at = read_at
    entry.version += 1
    entry.save(update_fields=["facts", "source_url", "read_at", "changed_at", "version"])
    record(
        action="register_entry.changed",
        actor=actor,
        subject_type=ENTRY,
        subject_id=entry.id,
        subject_title=facts.name,
        summary="A public register's facts on a company changed.",
        tenant_id=entry.tenant_id,
        before={"listed": old.listed, "version": entry.version - 1},
        after={**_diff(old, facts), "listed": facts.listed, "version": entry.version},
    )


def recheck(tenant_id: uuid.UUID) -> None:
    """Read the register again for every register entry of the bank's active legal entities,
    inside the bank's own transaction: a change is stored with its audit event, an unchanged
    read moves the read date, and a register that cannot be read is skipped until tomorrow.
    Then the scope follows the organisation (D-122)."""
    entries = list(
        RegisterEntry.objects.select_for_update(of=("self",))
        .select_related("authority")
        .filter(tenant_id=tenant_id, org_unit__active=True)
        .order_by("org_unit", "authority", "id")
    )
    if not entries:
        return
    registers = get_registers()
    actor = Actor.system("register re-read")
    deadline = _clock() + settings.REGISTERS_JOB_SECONDS
    with batched():
        for entry in entries:
            if _clock() > deadline:
                # The rest keep their facts and read date, and are read again tomorrow.
                logger.warning("register re-read stopped at its time limit", extra={"register_entry_id": str(entry.id)})
                break
            stored = RegisterFacts.model_validate(entry.facts)
            now = timezone.now()
            try:
                if not REGISTRATION_NUMBER.fullmatch(stored.registration_number):
                    raise RegisterUnavailable("the stored number cannot be looked up")
                read = registers.licence_facts(entry.authority.key, stored.registration_number)
            except RegisterUnavailable:
                logger.warning("register re-read skipped", extra={"register_entry_id": str(entry.id)})
                continue
            if read is None:
                fresh = stored.model_copy(update={"licences": [], "branches": [], "listed": False})
            else:
                fresh = registers_logic.register_facts(entry.authority.key, read)
            if _stored(fresh) != entry.facts:
                _change(entry, fresh, read.source_url if read is not None else entry.source_url, now, actor)
                continue
            entry.read_at = now
            entry.save(update_fields=["read_at"])
            record(
                action="register_entry.read",
                actor=actor,
                subject_type=ENTRY,
                subject_id=entry.id,
                subject_title=stored.name,
                summary="A public register was read again and nothing had changed.",
                tenant_id=entry.tenant_id,
                after={"readAt": now.isoformat()},
            )
        # What changed reaches the scope by itself (D-122); a register that could not be read changed nothing.
        organisation_scope.follow(tenant=Tenant.objects.get(pk=tenant_id))
