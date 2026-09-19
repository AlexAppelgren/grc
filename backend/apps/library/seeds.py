"""Reference seeds of the library app, run by `manage.py seed_reference` on every deploy
(playbook 12): idempotent, matched on the immutable key.

Languages (I18N-01, INPUT_DELTAS §3): the five content languages of R1 with the
PostgreSQL text search configuration their search chunks use (chunk 7). Without this
seed no label can be stored, every picker is empty and a tenant cannot set a default
language.

Jurisdictions (I18N-01, playbook 17, chunk 2): EU, SE, DK, NO, FI as rows with a parent,
a kind and the language their legal texts are written in, so no column or branch ever
names a country. Without this seed no instrument can be filed (chunk 3)."""

from __future__ import annotations

from apps.library.models import Jurisdiction, JurisdictionKind, JurisdictionLabel, Language

# key -> (name in its own language, PostgreSQL text search configuration)
# en: the original of every seeded label and the fallback in label_for().
# sv: Swedish, the prototype's first language and R1's second UI language.
# da: Danish, tenant B's language (Copenhagen).
# nb: Norwegian Bokmål; PostgreSQL ships one `norwegian` configuration.
# fi: Finnish, TEN-S1's language order.
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "english"),
    "sv": ("Svenska", "swedish"),
    "da": ("Dansk", "danish"),
    "nb": ("Norsk bokmål", "norwegian"),
    "fi": ("Suomi", "finnish"),
}

# key -> (kind, parent key, default language key, labels). Keys follow the fixture's codes
# lowercased (docs/inputs/schema.sql `jurisdiction`); Norway sits outside the Union.
JURISDICTIONS: dict[str, tuple[JurisdictionKind, str | None, str, dict[str, str]]] = {
    "eu": (JurisdictionKind.SUPRANATIONAL, None, "en", {"en": "European Union", "sv": "Europeiska unionen"}),
    "se": (JurisdictionKind.COUNTRY, "eu", "sv", {"en": "Sweden", "sv": "Sverige"}),
    "dk": (JurisdictionKind.COUNTRY, "eu", "da", {"en": "Denmark", "sv": "Danmark"}),
    "no": (JurisdictionKind.COUNTRY, None, "nb", {"en": "Norway", "sv": "Norge"}),
    "fi": (JurisdictionKind.COUNTRY, "eu", "fi", {"en": "Finland", "sv": "Finland"}),
}
DEFAULT_JURISDICTION = "eu"
# The language every seeded label is first written in: the original of its translation rows
# (D-12). A constant, so no line of code compares against a language literal (I18N-01).
ORIGINAL_LANGUAGE = "en"


def seed_languages() -> int:
    count = 0
    for key, (name, config) in LANGUAGES.items():
        Language.objects.update_or_create(key=key, defaults={"name": name, "text_search_config": config, "active": True})
        count += 1
    return count


def seed_jurisdictions() -> int:
    languages = {language.key: language for language in Language.objects.all()}
    rows: dict[str, Jurisdiction] = {}
    for sort_order, (key, (kind, parent_key, language_key, labels)) in enumerate(JURISDICTIONS.items()):
        row, created = Jurisdiction.objects.update_or_create(
            key=key,
            defaults={
                "kind": kind.value,
                "parent": rows[parent_key] if parent_key else None,
                "default_language": languages[language_key],
                "sort_order": sort_order,
                "is_system": True,
                "active": True,
                "is_default": key == DEFAULT_JURISDICTION,
            },
        )
        if created:
            for language, text in labels.items():
                JurisdictionLabel.objects.create(vocabulary=row, language=language, text=text, is_original=language == ORIGINAL_LANGUAGE)
        rows[key] = row
    return len(rows)
