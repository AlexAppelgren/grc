"""Field types the schema needs that Django no longer ships.

`CIEmailField` is a `citext` column, the custom field Django recommends since it removed
`CITextField`. The extension comes from shared 0001 (and infra/db/init.sql on template1).
Values are lower-cased in logic before they are stored, so the collation is a safety net.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.backends.base.base import BaseDatabaseWrapper


class CIEmailField(models.EmailField):
    def db_type(self, connection: BaseDatabaseWrapper) -> str:
        return "citext"

    def get_prep_value(self, value: Any) -> Any:
        prepared = super().get_prep_value(value)
        return prepared.strip().lower() if isinstance(prepared, str) else prepared
