"""Guard: no passwords and no Django admin (PRD ID-03, playbook 4.2, 4.3).

Enumerates the repository and the settings and demands: no `admin.py` under apps/, no
`django.contrib.auth` or `django.contrib.admin` in INSTALLED_APPS, no password validators,
no authentication backends, no model field named like a password, and no module that
calls Django's password hashing helpers. The emailed code is enrolment-only and lands in
chunk 1 as a hashed one-time value, never as a credential a person keeps.

Proven to fail 2026-09-19 by creating an empty apps/identity/admin.py: the test named it.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase

APPS_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = APPS_DIR.parent
HASHER_CALLS = re.compile(r"\b(make_password|check_password|set_password|set_unusable_password)\b")


class NoPasswordsGuard(SimpleTestCase):
    def test_no_admin_module_exists(self) -> None:
        found = sorted(str(p.relative_to(BACKEND_DIR)) for p in APPS_DIR.rglob("admin.py"))
        self.assertEqual(found, [], f"admin.py exists: {found}. The API is the only write surface (playbook 4.3).")

    def test_no_auth_or_admin_app_is_installed(self) -> None:
        installed = set(settings.INSTALLED_APPS)
        self.assertNotIn("django.contrib.auth", installed)
        self.assertNotIn("django.contrib.admin", installed)
        self.assertNotIn("django.contrib.sessions", installed)

    def test_no_password_machinery_is_configured(self) -> None:
        self.assertEqual(settings.AUTH_PASSWORD_VALIDATORS, [])
        self.assertEqual(settings.AUTHENTICATION_BACKENDS, [])
        # test_settings keeps the MD5 hasher for a stray contrib import (override 3); the
        # base settings hold none. Either way there is no auth app to use it.
        self.assertFalse(hasattr(settings, "AUTH_USER_MODEL") and settings.AUTH_USER_MODEL != "auth.User")

    def test_no_model_has_a_password_field(self) -> None:
        offenders = [
            f"{model._meta.label}.{field.name}"
            for model in apps.get_models()
            for field in model._meta.get_fields()
            if "password" in field.name.lower()
        ]
        self.assertEqual(offenders, [])

    def test_no_module_calls_password_hashing(self) -> None:
        offenders = []
        for path in APPS_DIR.rglob("*.py"):
            if path.name.startswith("tests_"):
                continue
            if HASHER_CALLS.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(BACKEND_DIR)))
        self.assertEqual(offenders, [], f"password hashing helpers used in: {offenders}")
