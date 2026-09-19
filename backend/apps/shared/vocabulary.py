"""The abstract `Vocabulary` model (VOC-01, playbook 15) and its label rows (D-12).

A vocabulary row: immutable `key`, optional fixed `kind`, labels per language as
translation rows, a `usage_note` written for people and agents alike, `sort_order`,
`active`, `is_system`, `is_default`. One generic endpoint set serves every list as
`{key, kind, label}`; nothing ever stores a label.

Concrete vocabularies (chunk 2 onward) subclass `Vocabulary` and declare a matching label
model that subclasses `VocabularyLabel` with a `vocabulary` foreign key named exactly so,
for example:

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

from apps.shared.tenancy import LibraryModel

# Content languages are rows (I18N-01); a label row references one by its code. The
# `language` table exists since chunk 1; the column stays a code (validated against the
# active rows by the logic that writes it) because turning it into a foreign key would
# rewrite the identity app's role label tables, which chunk 2 does not touch.
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
        # Retire, never delete (playbook 15). Merge re-points duplicates in chunk 2.
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
    """A tier-2 vocabulary (playbook 15): shared rows the platform curates, written only
    by an approved proposal (apps/proposals/apply.py) or a reference seed, because a
    change alters footprint matching and pickers for every tenant (VOC-07). The library
    fence (LibraryModel) refuses any other write. `version` backs If-Match on the
    proposal that relabels a row."""

    version = models.PositiveIntegerField(default=1)

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
    (VOC-02). `version` backs If-Match on PATCH. Declared apart from TenantVocabulary so
    the role tables of chunk 1 keep their column set."""

    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True
        ordering = ["sort_order", "key"]


def label_for(row: Vocabulary, language_order: list[str]) -> str:
    """The label in the first language of `language_order` that has one, then the
    original, then the key. Nothing stores a label, so a rename is instant."""
    labels = {label.language: label for label in row.labels.all()}  # type: ignore[attr-defined]
    for code in language_order:
        if code in labels:
            return labels[code].text
    for label in labels.values():
        if label.is_original:
            return label.text
    return row.key
