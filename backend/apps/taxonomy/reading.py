"""Reading vocabularies: the language order a caller sees labels in, and the one function
that turns a row into the `VocabularyRow` every surface renders (VOC-01, I18N-01).

Nothing here writes. It names no model class of its own: the list's model and label model
come from apps/taxonomy/registry.py, so one reader serves every list and adding a list is
adding a registry entry (AC-VOC1).

Labels are translation rows (D-12). The order is the caller's own language, then the
tenant's default, then `en`, then the original the row was written in, then the key: a
label is never stored on the record that uses it, so a rename is instant everywhere.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.http import HttpRequest
from pydantic.alias_generators import to_camel

from apps.shared.authentication import Principal, PrincipalKind
from apps.taxonomy.schemas import AgentRef

FALLBACK_LANGUAGE = "en"
# What `confirmation_of()` reads, joined into the row's own query so a page of rows costs
# no query per row (playbook 10). Only a library list or a term has these columns.
CONFIRMATION_JOINS = ("verified_by_agent", "applied_by_proposal__proposed_by_agent")


def language_order(request: HttpRequest, *, tenant: Any = None) -> list[str]:
    """The caller's content language order. Two queries at most: the person's locale and,
    when they are in one, the tenant's default language, unless the route already loaded
    the tenant (pass it; `caller_tenant` selects the default language with it). A platform
    session has no tenant and reads in its own locale, then `en`."""
    from apps.identity.models import User
    from apps.shared.models import Tenant

    principal = getattr(request, "auth", None)
    order: list[str] = []
    if isinstance(principal, Principal) and principal.kind is PrincipalKind.USER:
        row = User.objects.select_related("locale").filter(pk=principal.subject_id).first()  # ordering: pk lookup, at most one row
        if row is not None and row.locale is not None:
            order.append(row.locale.key)
        if principal.tenant_id is not None:
            if tenant is None or tenant.pk != principal.tenant_id:
                tenant = Tenant.objects.select_related("default_language").filter(pk=principal.tenant_id).first()  # ordering: pk lookup, at most one row
            if tenant is not None and tenant.default_language is not None:
                order.append(tenant.default_language.key)
    if FALLBACK_LANGUAGE not in order:
        order.append(FALLBACK_LANGUAGE)
    return order


def label_of(labels: dict[str, str], order: list[str], *, original: str | None, key: str) -> str:
    """The label in the first language of `order` that has one, then the original, then the
    key itself (never an empty string: an unlabelled row still renders)."""
    for code in order:
        if labels.get(code):
            return labels[code]
    if original and labels.get(original):
        return labels[original]
    for text in labels.values():
        if text:
            return text
    return key


class Labels:
    """Every label row of one list, grouped by the row it belongs to, read in one query."""

    def __init__(self, by_row: dict[uuid.UUID, list[Any]]) -> None:
        self._by_row = by_row

    @classmethod
    def for_rows(cls, label_model: type[Any], rows: list[Any], *, field: str = "vocabulary") -> Labels:
        by_row: dict[uuid.UUID, list[Any]] = {row.id: [] for row in rows}
        if not by_row:
            return cls(by_row)
        queryset = label_model._default_manager.filter(**{f"{field}_id__in": list(by_row)}).order_by("language")
        for label in queryset:
            by_row.setdefault(getattr(label, f"{field}_id"), []).append(label)
        return cls(by_row)

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
    (`slaDays`, `restrictsFootprint`). A foreign key is rendered as the related row's key."""
    values: dict[str, Any] = {}
    for name in fields:
        value: Any = getattr(row, name, None)
        if value is not None and hasattr(value, "key"):
            value = value.key
        values[to_camel(name)] = value
    return values


def confirmation_of(row: Any) -> dict[str, Any]:
    """Who confirmed the approval that wrote a library list row's or a term's current
    wording, and which agent proposed it (INV-05, PRO-02, D-62), as stored: the three
    provenance fields of `VocabularyRow` and `TaxonomyTermRow`, in the shape an obligation
    version's `VersionConfirmation` has. A bank's own list has no such columns and answers
    empty, as a seeded library row does. The label is the screen's to decide."""
    proposal = getattr(row, "applied_by_proposal", None)
    return {
        "verified_origin": getattr(row, "verified_origin", ""),
        "confirmed_by_agent": _agent_ref(getattr(row, "verified_by_agent", None)),
        "proposed_by_agent": _agent_ref(None if proposal is None else proposal.proposed_by_agent),
    }


def _agent_ref(agent: Any) -> AgentRef | None:
    return None if agent is None else AgentRef(id=agent.id, key=agent.key)
