"""Guard: vocabulary integrity (playbook 5, 15, VOC-01, VOC-04).

Enumerates every concrete `Vocabulary` subclass and demands: a matching label model
(translation rows, D-12) with a `vocabulary` foreign key; for every declared kind at
least one active system row; and at least one default row per list, so a category never
goes empty and a picker always has a default. Phase 0 has no concrete vocabulary; the
enumeration runs and finds none, and the abstract base's own rules (immutable key,
retire-never-delete) are proven on a throwaway model.

Proven to fail 2026-09-19 by defining a concrete vocabulary in apps/taxonomy/models.py
with no label model: the test named the vocabulary and what it lacked.
"""

from __future__ import annotations

from django.apps import apps
from django.db import ProgrammingError, connection, models, transaction
from apps.shared.testing import production_models
from django.test import TestCase

from apps.shared.vocabulary import Vocabulary, VocabularyLabel, label_for


def concrete_vocabularies() -> list[type[Vocabulary]]:
    return [m for m in production_models() if issubclass(m, Vocabulary) and not m._meta.abstract]


def label_model_for(vocabulary: type[Vocabulary]) -> type[VocabularyLabel] | None:
    for model in apps.get_models():
        if not issubclass(model, VocabularyLabel) or model._meta.abstract:
            continue
        field = next((f for f in model._meta.get_fields() if f.name == "vocabulary"), None)
        if field is not None and getattr(field, "related_model", None) is vocabulary:
            return model
    return None


class VocabularyIntegrityGuard(TestCase):
    def test_every_vocabulary_has_labels_system_rows_per_kind_and_a_default(self) -> None:
        problems: list[str] = []
        for vocabulary in concrete_vocabularies():
            name = vocabulary.__name__
            if label_model_for(vocabulary) is None:
                problems.append(f"{name}: no VocabularyLabel model with a `vocabulary` foreign key to it")
            kinds = [key for key, _ in getattr(vocabulary, "KIND_CHOICES", [])]
            try:
                with transaction.atomic():
                    for kind in kinds:
                        if not vocabulary._default_manager.filter(kind=kind, active=True, is_system=True).exists():
                            problems.append(f"{name}: kind {kind!r} has no active system row (seed one)")
                    if not vocabulary._default_manager.filter(is_default=True, active=True).exists():
                        problems.append(f"{name}: no active default row")
            except ProgrammingError:
                problems.append(f"{name}: table {vocabulary._meta.db_table} does not exist (no migration)")
        self.assertEqual(problems, [], "Vocabulary integrity problems:\n  " + "\n  ".join(problems))


class ProbeVocabulary(Vocabulary):
    """Throwaway concrete model for the base-class rules. Its table is created in the test."""

    objects: models.Manager[ProbeVocabulary] = models.Manager()

    class Meta:
        app_label = "shared"
        db_table = "probe_vocabulary"
        managed = False


class ProbeVocabularyLabel(VocabularyLabel):
    vocabulary = models.ForeignKey(ProbeVocabulary, on_delete=models.CASCADE, related_name="labels")
    objects: models.Manager[ProbeVocabularyLabel] = models.Manager()

    class Meta:
        app_label = "shared"
        db_table = "probe_vocabulary_label"
        managed = False


class VocabularyBaseRules(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(ProbeVocabulary)
            editor.create_model(ProbeVocabularyLabel)

    @classmethod
    def tearDownClass(cls) -> None:
        with connection.schema_editor() as editor:
            editor.delete_model(ProbeVocabularyLabel)
            editor.delete_model(ProbeVocabulary)
        super().tearDownClass()

    def test_the_key_is_immutable_and_rows_are_retired_not_deleted(self) -> None:
        row = ProbeVocabulary.objects.create(key="custody", kind=None, is_default=True)
        row.key = "custody-2"
        with self.assertRaises(Exception) as caught:  # compliance: allow-broad-except asserting the ValidationError subclass by code
            row.save()
        self.assertEqual(getattr(caught.exception, "code", None), "key_immutable")
        row.refresh_from_db()
        self.assertEqual(row.key, "custody")
        with self.assertRaises(Exception) as caught:  # compliance: allow-broad-except asserting the ValidationError subclass by code
            row.delete()
        self.assertEqual(getattr(caught.exception, "code", None), "retire_not_delete")
        row.active = False
        row.save()
        self.assertFalse(ProbeVocabulary.objects.get(pk=row.pk).active)

    def test_label_for_prefers_the_language_order_then_the_original_then_the_key(self) -> None:
        row = ProbeVocabulary.objects.create(key="advice")
        ProbeVocabularyLabel.objects.create(vocabulary=row, language="sv", text="Rådgivning", is_original=True)
        ProbeVocabularyLabel.objects.create(vocabulary=row, language="en", text="Advice", is_machine=True)
        self.assertEqual(label_for(row, ["en", "sv"]), "Advice")
        self.assertEqual(label_for(row, ["fi"]), "Rådgivning")
        bare = ProbeVocabulary.objects.create(key="lending")
        self.assertEqual(label_for(bare, ["en"]), "lending")
        self.assertIsNotNone(label_model_for(ProbeVocabulary))
