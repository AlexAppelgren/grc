"""Guard: production guard (playbook 5, 11.1).

Boots Django in a subprocess (`django.setup()`, which runs settings and every
AppConfig.ready, so the database role guard fires too) under different environment
names and variable combinations, and demands that an unrecognised environment name is
treated as production (fail closed): `prod`, `Production`, `demo` and `dev` all keep every
guard on, `local`, `test` and `ci` are the only non-deployed names, and a host environment
name alone makes any name deployed.

Two settings' bounds do not name an environment: LIBRARY_DIFF_MAX_SENTENCES is refused
outside 1 to 200 everywhere, because above 200 one "show what changed" can cost seconds on
text a source fetched, and API_PAGE_OFFSET_MAX is refused below API_PAGE_SIZE_MAX, because
under one page no reader reaches a list's second page. DEBUG never relaxes a bound.

Each case names the rule of the production-safety block it proves. The subprocess
environment is built from scratch (no inherited variable), so the runner's own settings
cannot leak in. Cases run three at a time; each is a ~1 s interpreter start.

Proven to fail 2026-09-19 by commenting out rule 4 in settings.py: the E2E case reported
"booted" where a refusal was expected.
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase

BOOT = "import django; django.setup(); print('booted')"
SETTING_NAMES = (
    "ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "DEBUG",
    "SECRET_KEY",
    "E2E_MODE",
    "WEBAUTHN_RP_ID",
    "WEBAUTHN_ORIGINS",
    "LLM_PROVIDER",
    "EMBEDDER_PROVIDER",
    "RERANKER_PROVIDER",
    "AGENT_RUNNER",
    "MAIL_PROVIDER",
    "STORAGE_BACKEND",
    "STORAGE_S3_BUCKET",
    "DATABASE_URL",
    "MIGRATOR_DATABASE_URL",
    "DB_ROLE_GUARD_ENABLED",
    "DJANGO_SETTINGS_MODULE",
    "SENTRY_DSN",
    "LIBRARY_DIFF_MAX_SENTENCES",
    "API_PAGE_OFFSET_MAX",
    "API_PAGE_SIZE_MAX",
    "RATE_LIMITING_ENABLED",
)


def _with_database(url: str, name: str) -> str:
    # The boots connect to 127.0.0.1, not "localhost": six of them resolving the name at
    # once on a loaded machine failed with "failed to resolve host 'localhost'" on
    # 2026-09-19. An address needs no lookup, so that failure cannot happen.
    parts = urlsplit(url)
    netloc = parts.netloc.replace("@localhost:", "@127.0.0.1:")
    return urlunsplit((parts.scheme, netloc, f"/{name}", parts.query, parts.fragment))


@dataclass(frozen=True)
class Case:
    name: str
    env: dict[str, str]
    expect_boot: bool
    expect_in_error: str = ""
    rule: str = ""
    extra: dict[str, str] = field(default_factory=dict)


class ProductionGuard(TestCase):
    databases = {DEFAULT_DB_ALIAS}
    app_url: str
    migrator_url: str
    superuser_url: str

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        test_db = connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]
        cls.app_url = _with_database(settings.DATABASE_URL, test_db)
        cls.migrator_url = _with_database(settings.MIGRATOR_DATABASE_URL, test_db)
        cls.superuser_url = _with_database(settings.TEST_SUPERUSER_DATABASE_URL, test_db)

    def _good_deployed(self, environment: str, **overrides: str) -> dict[str, str]:  # compliance: allow-kwargs test helper building an environment mapping
        env = {
            "ENVIRONMENT": environment,
            "DEBUG": "false",
            "SECRET_KEY": "a-real-looking-key-for-the-subprocess",
            "LLM_PROVIDER": "anthropic",
            "EMBEDDER_PROVIDER": "none",
            "RERANKER_PROVIDER": "none",
            "AGENT_RUNNER": "managed_agents",
            "MAIL_PROVIDER": "smtp",
            "STORAGE_BACKEND": "s3",
            "STORAGE_S3_BUCKET": "bucket",
            "WEBAUTHN_RP_ID": "compliance.example.test",
            "WEBAUTHN_ORIGINS": "https://compliance.example.test",
            "DATABASE_URL": self.app_url,
            "MIGRATOR_DATABASE_URL": self.migrator_url,
        }
        env.update(overrides)
        return env

    def _local(self, environment: str, **overrides: str) -> dict[str, str]:  # compliance: allow-kwargs test helper building an environment mapping
        env = {
            "ENVIRONMENT": environment,
            "DEBUG": "true",
            "DATABASE_URL": self.app_url,
            "MIGRATOR_DATABASE_URL": self.migrator_url,
        }
        env.update(overrides)
        return env

    def _boot(self, case: Case) -> tuple[Case, subprocess.CompletedProcess[str]]:
        env = {k: v for k, v in os.environ.items() if k not in SETTING_NAMES}
        env.update(case.env)
        env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, "-c", BOOT],
            cwd=str(settings.BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return case, result

    def cases(self) -> list[Case]:
        return [
            # Non-deployed names boot with mocks, DEBUG and the default key.
            Case("local boots", self._local("local"), True),
            Case("test boots", self._local("test"), True),
            Case("ci boots", self._local("ci"), True),
            # A properly configured deployed environment boots, under every deployed name.
            Case("prod boots when configured", self._good_deployed("prod"), True),
            Case("Production boots when configured", self._good_deployed("Production"), True),
            Case("demo boots when configured", self._good_deployed("demo"), True),
            Case("dev boots when configured", self._good_deployed("dev"), True),
            # Rule 1: the host name alone makes `local` deployed; mocks are then refused.
            Case(
                "host name makes local deployed",
                self._local("local", RAILWAY_ENVIRONMENT_NAME="staging", DEBUG="false", SECRET_KEY="k"),
                False,
                "mock adapter",
                "rule 1 and 5",
            ),
            # Rule 2: DEBUG on any deployed name.
            Case("prod refuses DEBUG", self._good_deployed("prod", DEBUG="true"), False, "DEBUG=True", "rule 2"),
            Case("dev refuses DEBUG", self._good_deployed("dev", DEBUG="true"), False, "DEBUG=True", "rule 2"),
            Case("demo refuses DEBUG", self._good_deployed("demo", DEBUG="true"), False, "DEBUG=True", "rule 2"),
            Case(
                "Production refuses DEBUG",
                self._good_deployed("Production", DEBUG="true"),
                False,
                "DEBUG=True",
                "rule 2",
            ),
            # Rule 3: missing or default SECRET_KEY on any deployed name; accepted on local/test/ci
            # (CI runs with no key), and DEBUG plays no part either way.
            Case("prod refuses missing key", self._good_deployed("prod", SECRET_KEY=""), False, "SECRET_KEY", "rule 3"),
            Case(
                "demo refuses the default key even under DEBUG-off",
                self._good_deployed("demo", SECRET_KEY="django-insecure-dev-only-change-me"),
                False,
                "SECRET_KEY",
                "rule 3",
            ),
            Case("ci boots with no key and DEBUG off", self._local("ci", DEBUG="false"), True),
            Case(
                "host name refuses the default key",
                self._local("ci", DEBUG="false", RAILWAY_ENVIRONMENT_NAME="ci", LLM_PROVIDER="anthropic",
                            EMBEDDER_PROVIDER="none", RERANKER_PROVIDER="none", AGENT_RUNNER="managed_agents",
                            MAIL_PROVIDER="smtp",
                            STORAGE_BACKEND="s3", STORAGE_S3_BUCKET="b"),
                False,
                "SECRET_KEY",
                "rule 1 and 3",
            ),
            # Rule 4: E2E_MODE when deployed, even on the test environment.
            Case("prod refuses E2E_MODE", self._good_deployed("prod", E2E_MODE="1"), False, "E2E_MODE", "rule 4"),
            Case(
                "deployed test refuses E2E_MODE",
                self._good_deployed("test", RAILWAY_ENVIRONMENT_NAME="test", E2E_MODE="true"),
                False,
                "E2E_MODE",
                "rule 4",
            ),
            Case("local allows E2E_MODE", self._local("local", E2E_MODE="true"), True),
            # Rule 8: a deployed environment must name its WebAuthn host (ADR 0002).
            Case(
                "prod refuses a localhost RP ID",
                self._good_deployed("prod", WEBAUTHN_RP_ID="localhost"),
                False,
                "WEBAUTHN_RP_ID",
                "rule 8",
            ),
            Case(
                "prod refuses a localhost origin",
                self._good_deployed("prod", WEBAUTHN_ORIGINS="http://localhost:3000"),
                False,
                "WEBAUTHN_RP_ID",
                "rule 8",
            ),
            Case("local allows the localhost RP ID", self._local("local", WEBAUTHN_RP_ID="localhost"), True),
            # Rule 5: mocks only on the deployed environment named test.
            Case(
                "prod refuses mock mailer",
                self._good_deployed("prod", MAIL_PROVIDER="mock"),
                False,
                "MAIL_PROVIDER",
                "rule 5",
            ),
            Case(
                "prod refuses mock llm and runner",
                self._good_deployed("prod", LLM_PROVIDER="mock", AGENT_RUNNER="mock"),
                False,
                "LLM_PROVIDER, AGENT_RUNNER",
                "rule 5",
            ),
            Case(
                "prod refuses the mock reranker",
                self._good_deployed("prod", RERANKER_PROVIDER="mock"),
                False,
                "RERANKER_PROVIDER",
                "rule 5",
            ),
            Case(
                "deployed test allows mocks",
                self._good_deployed(
                    "test",
                    RAILWAY_ENVIRONMENT_NAME="test",
                    LLM_PROVIDER="mock",
                    EMBEDDER_PROVIDER="mock",
                    RERANKER_PROVIDER="mock",
                    AGENT_RUNNER="mock",
                    MAIL_PROVIDER="mock",
                ),
                True,
            ),
            # Rule 6: local storage when deployed.
            Case(
                "prod refuses local storage",
                self._good_deployed("prod", STORAGE_BACKEND="local"),
                False,
                "STORAGE_BACKEND=local",
                "rule 6",
            ),
            # Rule 7: the database role, checked at boot on the live connection.
            Case(
                "prod refuses a superuser role",
                self._good_deployed("prod", DATABASE_URL=self.superuser_url),
                False,
                "superuser",
                "rule 7",
            ),
            Case(
                "prod refuses the migrator role",
                self._good_deployed("prod", DATABASE_URL=self.migrator_url),
                False,
                "owns tables",
                "rule 7",
            ),
            Case(
                "local refuses the migrator role too",
                self._local("local", DATABASE_URL=self.migrator_url),
                False,
                "owns tables",
                "rule 7: DEBUG never disarms a guard",
            ),
            # The sentence cap's bounds (H12): a setting, not a literal, but not any number.
            Case(
                "a diff cap of 0 refuses to boot",
                self._local("local", LIBRARY_DIFF_MAX_SENTENCES="0"),
                False,
                "LIBRARY_DIFF_MAX_SENTENCES",
                "the diff cap's bounds",
            ),
            Case(
                "a negative diff cap refuses to boot",
                self._local("local", LIBRARY_DIFF_MAX_SENTENCES="-1"),
                False,
                "LIBRARY_DIFF_MAX_SENTENCES",
                "the diff cap's bounds",
            ),
            Case(
                "a diff cap above 200 refuses to boot",
                self._good_deployed("prod", LIBRARY_DIFF_MAX_SENTENCES="201"),
                False,
                "LIBRARY_DIFF_MAX_SENTENCES",
                "the diff cap's bounds",
            ),
            Case("the diff cap boots at its ceiling", self._local("local", LIBRARY_DIFF_MAX_SENTENCES="200"), True),
            # The offset bound (H1): below one page nobody reaches the second page of a
            # list, and every list answers 422 to a number a caller cannot avoid.
            Case(
                "an offset bound below one page refuses to boot",
                self._local("local", API_PAGE_OFFSET_MAX="50", API_PAGE_SIZE_MAX="100"),
                False,
                "API_PAGE_OFFSET_MAX",
                "the offset bound's floor",
            ),
            Case(
                "a negative offset bound refuses to boot",
                self._good_deployed("prod", API_PAGE_OFFSET_MAX="-1"),
                False,
                "API_PAGE_OFFSET_MAX",
                "the offset bound's floor",
            ),
            Case(
                "the offset bound boots at its floor",
                self._local("local", API_PAGE_OFFSET_MAX="100", API_PAGE_SIZE_MAX="100"),
                True,
            ),
            # Rule 9 (security-review-c7, M2): one variable must not switch off every rate
            # limit at once, the sign-in ceremonies' and the model spend's alike.
            Case(
                "rate limiting switched off refuses to boot when deployed",
                self._good_deployed("prod", RATE_LIMITING_ENABLED="false"),
                False,
                "RATE_LIMITING_ENABLED",
                "rule 9",
            ),
            Case(
                "rate limiting switched off still boots on a laptop",
                self._local("local", RATE_LIMITING_ENABLED="false"),
                True,
            ),
            Case(
                "DB_ROLE_GUARD_ENABLED=false does not disarm rule 7 when deployed",
                self._good_deployed("prod", DATABASE_URL=self.superuser_url, DB_ROLE_GUARD_ENABLED="false"),
                False,
                "superuser",
                "rule 7 (see settings: the env override is refused when deployed)",
            ),
        ]

    def test_every_case_boots_or_refuses_as_the_rules_say(self) -> None:
        cases = self.cases()
        # Three at a time: each boot starts an interpreter and opens a database connection,
        # and six at once on a loaded machine lost one with empty output (2026-09-19).
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(self._boot, cases))
        failures: list[str] = []
        for case, result in results:
            booted = result.returncode == 0 and "booted" in result.stdout
            if case.expect_boot and not booted:
                failures.append(f"{case.name}: expected boot, got exit {result.returncode}\n{result.stderr[-800:]}")
            elif not case.expect_boot:
                if booted:
                    failures.append(f"{case.name}: expected refusal ({case.rule}), but it booted")
                elif case.expect_in_error not in result.stderr:
                    failures.append(
                        f"{case.name}: refused, but not for {case.expect_in_error!r} ({case.rule})\n{result.stderr[-800:]}"
                    )
        self.assertEqual(failures, [], "\n\n".join(failures))
