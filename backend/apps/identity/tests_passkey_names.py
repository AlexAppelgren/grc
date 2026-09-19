"""A new passkey is named from what the registration already tells us (PRD ID-04; Alex,
2026-09-19: "Can we remove this step and automatically use the device name / information
instead."). The authenticator's AAGUID first, the browser and platform second, the
transport last; unique per person with a counter. An explicit nickname still wins, and
renaming stays (ID-S10)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.identity import passkey_names
from apps.identity.models import WebAuthnCredential
from apps.identity.passkey_names import derive_nickname, describe_browser, unique_among
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.shared import factories
from apps.shared.models import AuditEvent
from apps.shared.testing import sign_in

WINDOWS_HELLO = "08987058-cadc-4b81-b6e1-30de50dcbe96"
GOOGLE_PASSWORD_MANAGER = "ea9b8d66-4d01-1d21-3ce4-b6b48cb575d4"
ONE_PASSWORD = "bada5566-a7aa-401f-bd96-45619a55120d"
APPLE_PASSWORDS = "fbfc3007-154e-4ecc-8c0b-6e020557d7bd"
ZERO = "00000000-0000-0000-0000-000000000000"
UNLISTED = "2fc0579f-8113-47ea-b116-bb5a8db9202a"  # a hardware key's AAGUID; hardware keys are not vendored

CHROME_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
EDGE_WINDOWS = CHROME_WINDOWS + " Edg/140.0.0.0"
SAFARI_MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15"
SAFARI_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1"
CHROME_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0.0.0 Mobile/15E148 Safari/604.1"
CHROME_ANDROID = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0"
SAMSUNG_ANDROID = "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/28.0 Chrome/130.0.0.0 Mobile Safari/537.36"
CHROMEOS = "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"


def derive(aaguid: str = ZERO, user_agent: str = "", transports: tuple[str, ...] = ("internal", "hybrid"), attachment: str | None = "platform", taken: tuple[str, ...] = ()) -> passkey_names.DerivedName:
    return derive_nickname(aaguid=aaguid, user_agent=user_agent, transports=list(transports), attachment=attachment, taken=list(taken))


class AuthenticatorNameFirst(SimpleTestCase):
    def test_a_known_aaguid_names_the_passkey_after_its_provider(self) -> None:
        for aaguid, name in [
            (WINDOWS_HELLO, "Windows Hello"),
            (GOOGLE_PASSWORD_MANAGER, "Google Password Manager"),
            (ONE_PASSWORD, "1Password"),
            (APPLE_PASSWORDS, "Apple Passwords"),
        ]:
            with self.subTest(name):
                derived = derive(aaguid, user_agent=CHROME_WINDOWS)
                self.assertEqual((derived.nickname, derived.source), (name, passkey_names.SOURCE_AUTHENTICATOR))

    def test_the_aaguid_is_matched_whatever_its_case(self) -> None:
        self.assertEqual(derive(WINDOWS_HELLO.upper()).nickname, "Windows Hello")

    def test_a_known_aaguid_wins_even_for_a_roaming_authenticator(self) -> None:
        derived = derive(ONE_PASSWORD, user_agent=CHROME_WINDOWS, transports=("hybrid",), attachment="cross-platform")
        self.assertEqual(derived.nickname, "1Password")


class BrowserAndPlatformSecond(SimpleTestCase):
    def test_an_unknown_zero_or_missing_aaguid_falls_back_to_the_user_agent(self) -> None:
        for aaguid in (UNLISTED, ZERO, "", "not-an-aaguid"):
            with self.subTest(aaguid=aaguid):
                derived = derive(aaguid, user_agent=CHROME_WINDOWS)
                self.assertEqual((derived.nickname, derived.source), ("Chrome on Windows", passkey_names.SOURCE_BROWSER))

    def test_the_user_agent_is_read_by_hand_in_a_fixed_order(self) -> None:
        # Edge and Samsung Internet carry "Chrome/" too; Android carries "Linux"; an
        # iPhone carries "Mac OS X". The first match in each table wins.
        for user_agent, expected in [
            (CHROME_WINDOWS, "Chrome on Windows"),
            (EDGE_WINDOWS, "Edge on Windows"),
            (SAFARI_MAC, "Safari on macOS"),
            (SAFARI_IPHONE, "Safari on iPhone"),
            (CHROME_IPHONE, "Chrome on iPhone"),
            (CHROME_ANDROID, "Chrome on Android"),
            (SAMSUNG_ANDROID, "Samsung Internet on Android"),
            (FIREFOX_LINUX, "Firefox on Linux"),
            (CHROMEOS, "Chrome on ChromeOS"),
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Windows"),
            ("Firefox/142.0", "Firefox"),
        ]:
            with self.subTest(expected):
                self.assertEqual(describe_browser(user_agent), expected)

    def test_an_unrecognised_user_agent_is_never_used_as_a_name(self) -> None:
        for user_agent in ("curl/8.9.1", "python-requests/2.32", "   ", ""):
            with self.subTest(user_agent=user_agent):
                self.assertIsNone(describe_browser(user_agent))
                self.assertEqual(derive(user_agent=user_agent).nickname, "Passkey")

    def test_a_roaming_authenticator_is_not_named_after_the_browser_that_registered_it(self) -> None:
        # A security key or a phone moves between computers: "Chrome on Windows" would name
        # the computer, not the passkey.
        self.assertEqual(derive(UNLISTED, user_agent=CHROME_WINDOWS, transports=("usb",), attachment="cross-platform").nickname, "Security key")
        self.assertEqual(derive(ZERO, user_agent=CHROME_WINDOWS, transports=("hybrid", "internal"), attachment="cross-platform").nickname, "Phone")
        # Without the attachment, transports without "internal" say the same thing.
        self.assertEqual(derive(UNLISTED, user_agent=SAFARI_MAC, transports=("nfc", "usb"), attachment=None).nickname, "Security key")


class TransportLast(SimpleTestCase):
    def test_a_missing_user_agent_falls_back_to_the_transport(self) -> None:
        for transports, attachment, expected in [
            (("usb",), "cross-platform", "Security key"),
            (("nfc",), None, "Security key"),
            (("ble",), None, "Security key"),
            (("usb", "nfc"), None, "Security key"),
            (("hybrid",), None, "Phone"),
            (("hybrid", "internal"), "cross-platform", "Phone"),
            (("hybrid", "internal"), "platform", "Passkey"),
            (("internal",), "platform", "Passkey"),
            ((), None, "Passkey"),
            (("smart-card",), None, "Passkey"),
        ]:
            with self.subTest(transports=transports, attachment=attachment):
                derived = derive(UNLISTED, user_agent="", transports=transports, attachment=attachment)
                self.assertEqual((derived.nickname, derived.source), (expected, passkey_names.SOURCE_TRANSPORT))


class UniquePerPerson(SimpleTestCase):
    def test_a_name_already_held_gets_a_counter(self) -> None:
        self.assertEqual(unique_among("Windows Hello", []), "Windows Hello")
        self.assertEqual(unique_among("Windows Hello", ["Windows Hello"]), "Windows Hello (2)")
        self.assertEqual(unique_among("Windows Hello", ["windows hello", "WINDOWS HELLO (2)", "Laptop"]), "Windows Hello (3)")
        self.assertEqual(unique_among("Windows Hello", ["Windows Hello (2)"]), "Windows Hello", "only the name itself counts as taken")

    def test_the_counter_applies_to_every_derived_name(self) -> None:
        self.assertEqual(derive(APPLE_PASSWORDS, taken=("Apple Passwords",)).nickname, "Apple Passwords (2)")
        self.assertEqual(derive(user_agent=SAFARI_MAC, taken=("Safari on macOS",)).nickname, "Safari on macOS (2)")
        self.assertEqual(derive(transports=("usb",), attachment=None, taken=("Security key", "Security key (2)")).nickname, "Security key (3)")

    def test_the_counter_fits_the_column(self) -> None:
        long = "x" * passkey_names.NICKNAME_MAX_LENGTH
        renamed = unique_among(long, [long])
        self.assertEqual(len(renamed), passkey_names.NICKNAME_MAX_LENGTH)
        self.assertTrue(renamed.endswith(" (2)"))


class VendoredAaguidNames(SimpleTestCase):
    def test_the_data_file_is_well_formed_and_names_its_source(self) -> None:
        names = passkey_names.aaguid_names()
        self.assertGreaterEqual(len(names), 50)
        pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        for aaguid, name in names.items():
            self.assertRegex(aaguid, pattern)
            self.assertTrue(name and name == name.strip() and len(name) <= passkey_names.NICKNAME_MAX_LENGTH, aaguid)
        self.assertNotIn(ZERO, names)
        header = passkey_names.AAGUID_NAMES_FILE.read_text(encoding="utf-8")
        for needle in ("github.com/passkeydeveloper/passkey-authenticator-aaguids", "Licence:", "Fetched:  2026-09-19"):
            self.assertIn(needle, header)

    def test_a_malformed_data_file_refuses_to_load(self) -> None:
        with TemporaryDirectory() as folder:
            broken = Path(folder) / "names.tsv"
            broken.write_text("# header\n08987058-CADC-4b81-b6e1-30de50dcbe96 Windows Hello\n", encoding="utf-8")
            with mock.patch.object(passkey_names, "AAGUID_NAMES_FILE", broken):
                passkey_names.aaguid_names.cache_clear()
                try:
                    with self.assertRaises(ImproperlyConfigured):
                        passkey_names.aaguid_names()
                finally:
                    passkey_names.aaguid_names.cache_clear()


class RegistrationNamesThePasskey(TestCase):
    """Through the API: a blank or missing nickname is derived, never stored empty; an
    explicit one is stored as given."""

    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.user = factories.member(self.tenant).user
        factories.passkey(self.user, nickname="Chrome on Windows")
        self.headers = sign_in(self.user, tenant=self.tenant, step_up=True)

    def _register(self, body_extra: dict[str, object], authenticator: SoftwareAuthenticator | None = None, user_agent: str = CHROME_WINDOWS) -> dict[str, object]:
        options = self.client.post("/api/v1/auth/passkeys/register/options", **self.headers)
        self.assertEqual(options.status_code, 200, options.content)
        credential = (authenticator or SoftwareAuthenticator()).register(options.json())
        response = self.client.post(
            "/api/v1/auth/passkeys/register/verify",
            data={"credential": credential, **body_extra},
            content_type="application/json",
            HTTP_USER_AGENT=user_agent,
            **self.headers,
        )
        self.assertEqual(response.status_code, 201, response.content)
        passkey: dict[str, object] = response.json()["passkey"]
        return passkey

    def test_a_blank_nickname_is_derived_not_stored_empty(self) -> None:
        bodies: list[dict[str, object]] = [{"nickname": ""}, {"nickname": "   "}, {"nickname": None}, {}]
        for extra in bodies:
            with self.subTest(extra=extra):
                self._register(extra)
        stored = list(WebAuthnCredential.objects.filter(user=self.user).values_list("nickname", flat=True))
        self.assertEqual(stored, ["Chrome on Windows", "Chrome on Windows (2)", "Chrome on Windows (3)", "Chrome on Windows (4)", "Chrome on Windows (5)"])

    def test_the_authenticator_names_the_passkey_through_the_api(self) -> None:
        passkey = self._register({}, SoftwareAuthenticator(aaguid=uuid.UUID(GOOGLE_PASSWORD_MANAGER).bytes))
        self.assertEqual(passkey["nickname"], "Google Password Manager")
        event = AuditEvent.objects.filter(action="passkey.registered").order_by("-created").first()
        assert event is not None
        self.assertEqual((event.after or {}).get("nicknameSource"), passkey_names.SOURCE_AUTHENTICATOR)

    def test_an_explicit_nickname_is_stored_as_given(self) -> None:
        passkey = self._register({"nickname": "  Chrome on Windows  "})
        self.assertEqual(passkey["nickname"], "Chrome on Windows", "a chosen name is the person's; no counter is added")
        event = AuditEvent.objects.filter(action="passkey.registered").order_by("-created").first()
        assert event is not None
        self.assertEqual((event.after or {}).get("nicknameSource"), passkey_names.SOURCE_SUPPLIED)

    def test_a_security_key_is_named_from_its_transport(self) -> None:
        passkey = self._register({}, SoftwareAuthenticator(aaguid=uuid.UUID(UNLISTED).bytes, transports=("usb",), attachment="cross-platform"))
        self.assertEqual(passkey["nickname"], "Security key")

    def test_retired_passkeys_do_not_hold_a_name(self) -> None:
        retired = factories.passkey(self.user, nickname="Safari on macOS")
        retired.retired_at = timezone.now()
        retired.save(update_fields=["retired_at"])
        self.assertEqual(self._register({}, user_agent=SAFARI_MAC)["nickname"], "Safari on macOS")
