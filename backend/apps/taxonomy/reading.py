"""Reading vocabularies: the language order a caller sees labels in, and the one function
that turns a row into the `VocabularyRow` every surface renders (VOC-01, I18N-01).

Nothing here writes. Models come from apps/taxonomy/registry.py, so adding a list is adding a
registry entry (AC-VOC1). Labels are translation rows (D-12), in the order: the caller's
language, the tenant's default, `en`, the original, then the key.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.http import HttpRequest
from pydantic.alias_generators import to_camel

from apps.shared import tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.middleware import request_memo
from apps.taxonomy.schemas import AgentRef

FALLBACK_LANGUAGE = "en"
# What `confirmation_of()` reads, joined into the row's own query so a page of rows costs
# no query per row (playbook 10). Only a library list or a term has these columns.
CONFIRMATION_JOINS = ("verified_by_agent", "applied_by_proposal__proposed_by_agent")


def language_order(request: HttpRequest, *, tenant: Any = None) -> list[str]:
    """The caller's content language order: the person's locale and, in a tenant, its
    default language. Both come with the session's own read, so this costs no query unless a
    stubbed principal lacks them. A platform session reads in its own locale, then `en`."""
    from apps.identity.models import User
    from apps.shared.models import Tenant

    principal = getattr(request, "auth", None)
    order: list[str] = []
    if isinstance(principal, Principal) and principal.kind is PrincipalKind.USER:
        row = principal.user
        if row is None:
            row = User.objects.select_related("locale").filter(pk=principal.subject_id).first()  # ordering: pk lookup, at most one row
        if row is not None and row.locale is not None:
            order.append(row.locale.key)
        if principal.tenant_id is not None:
            if tenant is None or tenant.pk != principal.tenant_id:
                tenant = principal.tenant
            if tenant is None:
                tenant = Tenant.objects.select_related("default_language").filter(pk=principal.tenant_id).first()  # ordering: pk lookup, at most one row
            if tenant is not None and tenant.default_language is not None:
                order.append(tenant.default_language.key)
    if FALLBACK_LANGUAGE not in order:
        order.append(FALLBACK_LANGUAGE)
    return order


class Labels:
    """Every label row of one list, grouped by the row it belongs to, read in one query."""

    def __init__(self, by_row: dict[uuid.UUID, list[Any]]) -> None:
        self._by_row = by_row

    @classmethod
    def for_rows(cls, label_model: type[Any], rows: list[Any], *, field: str = "vocabulary") -> Labels:
        """Inside a read request a row's labels are read once (the request memo,
        apps/shared/middleware.py, keyed by the active tenant too, so one bank's labels never
        answer another's). Anywhere else, every call reads."""
        by_row: dict[uuid.UUID, list[Any]] = {row.id: [] for row in rows}
        memo = request_memo()
        known: dict[uuid.UUID, list[Any]] = {} if memo is None else memo.setdefault(("labels", label_model, field, tenancy.active_tenant_id()), {})
        missing = [row_id for row_id in by_row if row_id not in known]
        if missing:
            queryset = label_model._default_manager.filter(**{f"{field}_id__in": missing}).order_by("language")
            for label in queryset:
                by_row[getattr(label, f"{field}_id")].append(label)
            known.update({row_id: by_row[row_id] for row_id in missing})
        return cls({row_id: known.get(row_id, by_row[row_id]) for row_id in by_row})

    def texts(self, row_id: uuid.UUID) -> dict[str, str]:
        return {label.language: label.text for label in self._by_row.get(row_id, ())}

    def original(self, row_id: uuid.UUID) -> str | None:
        for label in self._by_row.get(row_id, ()):
            if label.is_original:
                return str(label.language)
        return None

    def machine(self, row_id: uuid.UUID) -> list[str]:
        return [str(label.language) for label in self._by_row.get(row_id, ()) if label.is_machine]


def extra_of(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """The list's own columns, camelCased so `extra` reads like the rest of the API
    (`slaDays`, `restrictsFootprint`). A foreign key is rendered as the related row's key, and
    an id column (`orgUnitId`) as the id's text."""
    values: dict[str, Any] = {}
    for name in fields:
        value: Any = getattr(row, name, None)
        if value is not None and hasattr(value, "key"):
            value = value.key
        if isinstance(value, uuid.UUID):
            value = str(value)
        values[to_camel(name)] = value
    return values


def confirmation_of(row: Any) -> dict[str, Any]:
    """Who confirmed the approval that wrote a library list row's or a term's wording, and
    which agent proposed it (INV-05, PRO-02, D-62), as stored, in `VersionConfirmation`'s
    shape. A bank's own list and a seeded row answer empty. The label is the screen's."""
    return {
        "verified_origin": getattr(row, "verified_origin", ""),
        "confirmed_by_agent": agent_ref(getattr(row, "verified_by_agent", None)),
        "proposed_by_agent": proposing_agent(getattr(row, "applied_by_proposal", None)),
    }


def agent_ref(agent: Any) -> AgentRef | None:
    """An agent as a screen names it: by its definition key (AUD-02)."""
    return None if agent is None else AgentRef(id=agent.id, key=agent.key)


def proposing_agent(proposal: Any) -> AgentRef | None:
    """The agent that proposed what an applied proposal wrote, as a read of the shared
    library names it. Withheld when the proposal was made inside a bank, as the queue
    withholds it (PRO-03): a shared read never names who proposed on a bank's behalf."""
    if proposal is None or proposal.proposed_in_tenant:
        return None
    return agent_ref(proposal.proposed_by_agent)
