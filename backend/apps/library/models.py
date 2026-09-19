"""Models of the library app. Chunk 1 adds `Language` (I18N-01, INPUT_DELTAS §3); chunk 2
adds `Jurisdiction` (I18N-01, playbook 17): the content languages and the jurisdictions
are rows, never a column check. Instruments, provisions, obligations and their versions
land in chunk 3 as LibraryModel subclasses.

`Language` and `Jurisdiction` are reference configuration, not sourced public facts:
they are written by `seed_reference` alone (apps/library/seeds.py) and read by everything
that labels, files or searches. They are therefore plain models rather than
`LibraryModel`s, so the tenant profile and role logic can name them beside their own
writes without tripping the library fence's AST heuristic
(apps/shared/tests_library_fence.py). `Jurisdiction` is a `Vocabulary` so it carries
labels per language and the immutable-key rule; its `kind` (supranational or country)
is the tier-one `JurisdictionKind`."""

from __future__ import annotations

import enum
import uuid

from django.db import models

from apps.shared.vocabulary import Vocabulary, VocabularyLabel


class Language(models.Model):
    """A content or UI language (I18N-01): immutable `key` (BCP 47 primary tag), a name
    in that language, the PostgreSQL text search configuration search chunks use, and an
    active flag. Seeded: en, sv, da, nb, fi."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=8, unique=True)
    name = models.CharField(max_length=80)
    text_search_config = models.CharField(max_length=40)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "language"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class JurisdictionKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): supranational (EU) or country."""

    SUPRANATIONAL = "supranational"
    COUNTRY = "country"


class Jurisdiction(Vocabulary):
    """A jurisdiction (I18N-01, schema v0.3 `jurisdiction`): `eu`, `se`, `dk`, `no`,
    `fi`, seeded with a parent (a country inside the Union) and the language its legal
    texts are written in. Instruments and authorities reference it from chunk 3."""

    KIND_CHOICES = [(kind.value, kind.value) for kind in JurisdictionKind]

    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    default_language = models.ForeignKey(Language, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "jurisdiction"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="jurisdiction_key_unique")]


class JurisdictionLabel(VocabularyLabel):
    vocabulary = models.ForeignKey(Jurisdiction, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "jurisdiction_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="jurisdiction_label_unique")]
