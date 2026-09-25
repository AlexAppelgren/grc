"""The collab mail catalog (COL-02, I18N-01): one dictionary of keys to plain-text templates
per language, the subject and body of each reminder, the escalation and the weekly digest,
plus the header and footer every one of them shares.

English and Swedish, which is what R2's banks read; `c13-i18n-server` adds da, nb and fi as
modules beside these two. Both catalogs hold exactly the same keys, which a test pins.

A placeholder names a field of `collab.mail.MailContext` (a record title, a date, a count, a
person's name or a link), or `recipient` and `product`, which the composer fills itself.
Nothing else can reach a mail, so no template can ask for a comment, a note or an
assessment (CHUNK10_TASKS rule 13).
"""

from __future__ import annotations

from apps.collab.mail_strings import en, sv

FALLBACK_LANGUAGE = "en"

CATALOGS: dict[str, dict[str, str]] = {"en": en.STRINGS, "sv": sv.STRINGS}
