"""The abstract `Vocabulary` model (VOC-01, playbook 15) and its label rows (D-12).

A vocabulary row: immutable `key`, optional fixed `kind`, labels per language as translation
rows, a `usage_note`, `sort_order`, `active`, `is_system`, `is_default`. One generic endpoint
set serves every list as `{key, kind, label}`; nothing ever stores a label.

A concrete vocabulary subclasses `Vocabulary` and declares a label model subclassing
`VocabularyLabel` with a `vocabulary` foreign key named exactly so:

    class ChangeType(LibraryVocabulary):
        class Kind(models.TextChoices): ...   # the fixed lifecycle kind, if any
        KIND_CHOICES = Kind.choices

    class ChangeTypeLabel(VocabularyLabel):
        vocabulary = models.ForeignKey(ChangeType, on_delete=models.CASCADE, related_name="labels")

The vocabulary-integrity guard checks every concrete vocabulary has its label model,
every kind has at least one active system row and every list has a default.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from apps.proposals.models import OriginType
from apps.shared.tenancy import LibraryModel

# Who confirmed a library row's wording: the `origin_type` kind the library's own
# provenance columns use (library 0007), so every confirmation reads the same two values.
ORIGIN_CHOICES = [(member.value, member.value) for member in OriginType]

# Content languages are rows (I18N-01); a label row names one by its code, validated against
# the active rows by the writing logic rather than a foreign key.
LANGUAGE_CODE_MAX_LENGTH = 8


class KeyIsImmutable(ValidationError):
    """A vocabulary key was changed after creation (playbook 4.3: stable keys)."""


class Vocabulary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=80)
    kind = models.CharField(max_length=40, null=True, blank=True)
    usage_note = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["sort_order", "key"]

    def __str__(self) -> str:
        return self.key

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        if not self._state.adding:
            stored = (
                type(self)._default_manager.filter(pk=self.pk).values_list("key", flat=True).first()
            )  # ordering: pk lookup, at most one row
            if stored is not None and stored != self.key:
                raise KeyIsImmutable(
                    "A vocabulary key never changes; rename the label instead.", code="key_immutable"
                )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        # Retire, never delete (playbook 15).
        raise ValidationError(
            "Vocabulary rows are retired, never deleted; set active=False.", code="retire_not_delete"
        )


class TenantVocabulary(Vocabulary):
    """A tier-3 vocabulary: rows one tenant manages, under forced RLS (playbook 15). Keys
    are unique per tenant. Declared here rather than by inheriting TenantModel beside
    Vocabulary so there is exactly one `id` and the tenant column is explicit."""

    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True
        ordering = ["sort_order", "key"]


class VocabularyLabel(models.Model):
    """One label of one vocabulary row in one language. `is_original` marks the language
    the row was written in; `is_machine` labels machine translations (D-12)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    language = models.CharField(max_length=LANGUAGE_CODE_MAX_LENGTH)
    text = models.CharField(max_length=200)
    is_original = models.BooleanField(default=False)
    is_machine = models.BooleanField(default=False)

    class Meta:
        abstract = True
        ordering = ["language"]

    def __str__(self) -> str:
        return f"{self.language}: {self.text}"


class LibraryVocabulary(Vocabulary, LibraryModel):
    """A tier-2 vocabulary (playbook 15): shared rows written only by an approved proposal or
    a reference seed, because a change alters matching and pickers for every tenant (VOC-07).
    `version` backs If-Match on a relabel proposal.

    Machine-confirmed provenance (INV-05, PRO-02, D-62, D-79), as on an obligation version:
    `verified_origin`, the confirming agent, and the proposal (through which the proposing
    agent is read). A row is reworded in place, so the stamp stays `agent` until a person has
    approved all the wording the agents left (`apply._restamp`); an approval writing no
    wording leaves it. Blank on a seeded row."""

    version = models.PositiveIntegerField(default=1)
    verified_origin = models.CharField(max_length=16, choices=ORIGIN_CHOICES, blank=True, default="")
    verified_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    applied_by_proposal = models.ForeignKey("proposals.Proposal", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True
        ordering = ["sort_order", "key"]


class LibraryVocabularyLabel(VocabularyLabel, LibraryModel):
    """A label of a library vocabulary row or taxonomy term: under the same fence as the
    row, because a relabel is a proposal (VOC-07)."""

    class Meta:
        abstract = True
        ordering = ["language"]


class TenantListVocabulary(TenantVocabulary):
    """A tier-3 vocabulary a tenant admin manages through the generic vocabulary routes
    (VOC-02). `version` backs If-Match on PATCH. Apart from TenantVocabulary so the role
    tables keep their column set."""

    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True
        ordering = ["sort_order", "key"]


def write_labels(label_model: type[Any], owner: dict[str, Any], labels: dict[str, str], *, is_machine: bool) -> None:
    """Write `labels` onto one row's translation rows (D-12); `owner` names the row. The first
    labels a row gets name its original: English when among them, else the first. `is_machine`
    is set by an agent's approval and cleared by a person's edit or approval, per label
    (INV-05, D-12, D-62)."""
    manager = label_model._default_manager
    existing = {label.language: label for label in manager.filter(**owner)}
    original = None
    if not any(label.is_original for label in existing.values()):
        original = "en" if "en" in labels else next(iter(labels), None)
    for language, text in labels.items():
        label = existing.get(language)
        if label is None:
            manager.create(**owner, language=language, text=text, is_original=language == original, is_machine=is_machine)
            continue
        label.text = text
        label.is_machine = is_machine
        label.save(update_fields=["text", "is_machine"])


def label_of(labels: dict[str, str], order: list[str], *, original: str | None, key: str) -> str:
    """The one label resolver: the label in the first language of `order` that has one, then
    the original, then any label, then the key itself (never an empty string: an unlabelled
    row still renders). Nothing stores a label, so a rename is instant."""
    for code in order:
        if labels.get(code):
            return labels[code]
    if original and labels.get(original):
        return labels[original]
    for text in labels.values():
        if text:
            return text
    return key


def label_for(row: Vocabulary, language_order: list[str]) -> str:
    """`label_of` over a row's own labels, read through its `labels` relation."""
    rows = list(row.labels.all())  # type: ignore[attr-defined]
    original = next((label.language for label in rows if label.is_original), None)
    return label_of({label.language: label.text for label in rows}, language_order, original=original, key=row.key)
