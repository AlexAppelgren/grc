"""Reference seeds of the library app, run by `manage.py seed_reference` on every deploy
(playbook 12): idempotent, matched on the immutable key.

Languages (I18N-01): the ten content languages with their PostgreSQL text search
configuration. Jurisdictions (I18N-01, playbook 17, D-145): the EU and the twelve home
markets, each with a parent, a kind and a legal language, so no code names a country, and
International (D-38) for standards bodies.

Every bank reads both, so the database holds them behind its doors (H16, ADR 0058): each
seed writes through `library_write()`. A jurisdiction's labels, sort order and `active` are
written only when the row is filed, since a proposal may change them (D-94)."""

from __future__ import annotations

from apps.library.models import Jurisdiction, JurisdictionKind, JurisdictionLabel, Language
from apps.shared.tenancy import library_write

# key -> (name in its own language, PostgreSQL text search configuration). en is the
# original of every seeded label and label_for()'s fallback; PostgreSQL ships one
# `norwegian` configuration, used for nb, and none for Estonian or Latvian, which are read
# word for word with `simple` (D-145).
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "english"),
    "sv": ("Svenska", "swedish"),
    "da": ("Dansk", "danish"),
    "nb": ("Norsk bokmål", "norwegian"),
    "fi": ("Suomi", "finnish"),
    "et": ("Eesti", "simple"),
    "lv": ("Latviešu", "simple"),
    "lt": ("Lietuvių", "lithuanian"),
    "de": ("Deutsch", "german"),
    "nl": ("Nederlands", "dutch"),
}

# key -> (kind, parent key, default language key, labels). The parent is the jurisdiction
# whose rules reach this one (D-28, ADR 0026): Norway points at the EU because EU financial
# rules reach it through the EEA Agreement. The United Kingdom and Switzerland have none:
# EU law reaches neither (D-145).
JURISDICTIONS: dict[str, tuple[JurisdictionKind, str | None, str, dict[str, str]]] = {
    "eu": (JurisdictionKind.SUPRANATIONAL, None, "en", {"en": "European Union", "sv": "Europeiska unionen"}),
    "se": (JurisdictionKind.COUNTRY, "eu", "sv", {"en": "Sweden", "sv": "Sverige"}),
    "dk": (JurisdictionKind.COUNTRY, "eu", "da", {"en": "Denmark", "sv": "Danmark"}),
    "no": (JurisdictionKind.COUNTRY, "eu", "nb", {"en": "Norway", "sv": "Norge"}),
    "fi": (JurisdictionKind.COUNTRY, "eu", "fi", {"en": "Finland", "sv": "Finland"}),
    # The other home markets (D-145). Switzerland enacts its law in German, French and
    # Italian alike; German is the one held.
    "ee": (JurisdictionKind.COUNTRY, "eu", "et", {"en": "Estonia", "sv": "Estland"}),
    "lv": (JurisdictionKind.COUNTRY, "eu", "lv", {"en": "Latvia", "sv": "Lettland"}),
    "lt": (JurisdictionKind.COUNTRY, "eu", "lt", {"en": "Lithuania", "sv": "Litauen"}),
    "de": (JurisdictionKind.COUNTRY, "eu", "de", {"en": "Germany", "sv": "Tyskland"}),
    "gb": (JurisdictionKind.COUNTRY, None, "en", {"en": "United Kingdom", "sv": "Storbritannien"}),
    "nl": (JurisdictionKind.COUNTRY, "eu", "nl", {"en": "Netherlands", "sv": "Nederländerna"}),
    "at": (JurisdictionKind.COUNTRY, "eu", "de", {"en": "Austria", "sv": "Österrike"}),
    "ch": (JurisdictionKind.COUNTRY, None, "de", {"en": "Switzerland", "sv": "Schweiz"}),
    # INV-01, INV-08 (D-38): the jurisdiction of an international standards body such as
    # ISO/IEC, no bank's own market. Its kind keeps it out of MIRRORED_JURISDICTION_KINDS
    # (apps/taxonomy/seeds), so it never offers "International" as an operating market. Last
    # in a new database; one seeded before D-145 keeps it in sixth place, since a row's place
    # is written once, until a proposal moves it (D-94).
    "intl": (JurisdictionKind.INTERNATIONAL, None, "en", {"en": "International", "sv": "Internationell"}),
}
DEFAULT_JURISDICTION = "eu"
# The language every seeded label is first written in: the original of its translation rows
# (D-12). A constant, so no line of code compares against a language literal (I18N-01).
ORIGINAL_LANGUAGE = "en"
SEED_REASON = "seed_reference"


def seed_languages() -> int:
    count = 0
    with library_write(SEED_REASON):
        for key, (name, config) in LANGUAGES.items():
            Language.objects.update_or_create(key=key, defaults={"name": name, "text_search_config": config, "active": True})
            count += 1
    return count


def seed_jurisdictions() -> int:
    languages = {language.key: language for language in Language.objects.all()}
    rows: dict[str, Jurisdiction] = {}
    with library_write(SEED_REASON):
        for sort_order, (key, (kind, parent_key, language_key, labels)) in enumerate(JURISDICTIONS.items()):
            # The kind, the parent and the legal language are the seed's on every run. The
            # sort order and `active` are written once: a proposal reorders, retires and
            # restores a jurisdiction (D-94), and no deploy may undo an approved decision.
            row, created = Jurisdiction.objects.update_or_create(
                key=key,
                defaults={
                    "kind": kind.value,
                    "parent": rows[parent_key] if parent_key else None,
                    "default_language": languages[language_key],
                    "is_system": True,
                    "is_default": key == DEFAULT_JURISDICTION,
                },
                create_defaults={
                    "kind": kind.value,
                    "parent": rows[parent_key] if parent_key else None,
                    "default_language": languages[language_key],
                    "is_system": True,
                    "is_default": key == DEFAULT_JURISDICTION,
                    "sort_order": sort_order,
                    "active": True,
                },
            )
            if created:
                for language, text in labels.items():
                    JurisdictionLabel.objects.create(vocabulary=row, language=language, text=text, is_original=language == ORIGINAL_LANGUAGE)
            rows[key] = row
    return len(rows)
