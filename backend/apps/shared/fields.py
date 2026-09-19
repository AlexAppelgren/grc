"""Field types the schema needs that Django no longer ships.

`CIEmailField` is a `citext` column (schema.sql: `email citext NOT NULL UNIQUE`). Django
removed its `CITextField` family in 5.1; the replacement it recommends is a custom field
whose `db_type` names the extension type, which is exactly this. The `citext` extension
is installed by shared 0001 (and by infra/db/init.sql on template1 for throwaway test
databases). Values are still normalised to lower case in logic before they are stored, so
the collation is a safety net, not the rule.
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
