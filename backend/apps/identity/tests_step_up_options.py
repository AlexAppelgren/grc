"""The passkey ceremony options carry no `null`: a browser converts them through WebIDL
before any authenticator is asked, and refuses a descriptor whose `transports` is `null`
("cannot be converted to a sequence"). Someone holding a passkey who opened a bank
invitation could not confirm joining, and could not add a second passkey (regression,
2026-11-09). Absent means "not given", which the documentation promises."""

from __future__ import annotations

from typing import Any

from django.core.cache import cache

from apps.library.seeds import seed_languages
from apps.shared import factories
from apps.shared.testing import ScenarioTestCase, sign_in


def nulls(value: Any, path: str = "$") -> list[str]:
    if value is None:
        return [path]
    if isinstance(value, dict):
        return [found for key, item in value.items() for found in nulls(item, f"{path}.{key}")]
    if isinstance(value, list):
        return [found for index, item in enumerate(value) for found in nulls(item, f"{path}[{index}]")]
    return []


class CeremonyOptionsShapeTests(ScenarioTestCase):
    def setUp(self) -> None:
        cache.clear()
        seed_languages()
        bank = factories.tenant(slug="bank-a")
        self.user = factories.member(bank, roles=("admin",)).user
        factories.passkey(self.user)
        self.headers = sign_in(self.user, tenant=bank)

    def _options(self, path: str, signed_in: bool = True) -> dict[str, Any]:
        response = self.client.post(f"/api/v1{path}", data={}, content_type="application/json", **(self.headers if signed_in else {}))
        self.assertEqual(response.status_code, 200, response.content)
        body: dict[str, Any] = response.json()
        return body

    def test_step_up_lists_the_passkey_without_nulls(self) -> None:
        options = self._options("/auth/step-up/options")
        self.assertEqual([sorted(item) for item in options["allowCredentials"]], [["id", "type"]])
        self.assertEqual(nulls(options), [])

    def test_adding_a_second_passkey_excludes_the_first_without_nulls(self) -> None:
        options = self._options("/auth/passkeys/register/options")
        self.assertEqual([sorted(item) for item in options["excludeCredentials"]], [["id", "type"]])
        self.assertEqual(nulls(options), [])

    def test_sign_in_options_carry_no_nulls(self) -> None:
        self.assertEqual(nulls(self._options("/auth/passkeys/authenticate/options", signed_in=False)), [])
