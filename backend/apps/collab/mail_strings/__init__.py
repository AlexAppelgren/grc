"""The collab mail catalog (COL-02, I18N-01): per language, the subject and body of each
reminder, the escalation and the digest, plus the shared header and footer. Both catalogs
hold the same keys (a test pins it).

A placeholder names a field of `collab.mail.MailContext`, or `recipient` and `product`, so no
template can ask for a comment, note or assessment (CHUNK10_TASKS rule 13).
"""

from __future__ import annotations

from apps.collab.mail_strings import en, sv

FALLBACK_LANGUAGE = "en"

CATALOGS: dict[str, dict[str, str]] = {"en": en.STRINGS, "sv": sv.STRINGS}
