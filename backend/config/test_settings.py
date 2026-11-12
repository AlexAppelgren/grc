"""Test settings (playbook 2.2): import everything, then override, each override with a
numbered reason. PostgreSQL with pgvector, never SQLite.

- `default` connects as cw_migrator, which owns the tables and may CREATEDB the throwaway
  `test_compliance_watch` (infra/db/init.sql).
- `app` connects as cw_app to the same database (TEST.MIRROR), with row-level security
  forced and no ownership, for the isolation and role proofs (`databases = {"default",
  "app"}`). Rows written in a TestCase transaction on `default` are invisible on `app`; use
  TransactionTestCase for committed rows.
"""

import os

# (0) The runner declares its own environment before the base settings evaluate the
#     production-safety block: non-deployed (the default key is then accepted, rule 3),
#     DEBUG off (10), E2E off (12). Real environment variables still win (setdefault), so
#     CI runs under ENVIRONMENT=ci with its own database URLs.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("E2E_MODE", "false")

from config.settings import *  # noqa: E402, F403  (1) import everything, override below
from config.settings import CELERY_BEAT_SCHEDULE, DATABASE_URL, MIGRATOR_DATABASE_URL, env_str  # noqa: E402

# (1) The runner creates the throwaway database as cw_migrator (CREATEDB, owns tables).
#     `app` mirrors it as cw_app so the RLS and role guards test the production role.
DATABASES = {
    "default": dj_database_url.parse(MIGRATOR_DATABASE_URL, conn_max_age=0),  # noqa: F405
    "app": dj_database_url.parse(DATABASE_URL, conn_max_age=0),  # noqa: F405
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
for _alias in DATABASES.values():
    _alias["OPTIONS"] = {**_alias.get("OPTIONS", {}), **JIT_OFF}  # noqa: F405  as the app runs
# Not ATOMIC_REQUESTS on `app`: Django would open the cw_app connection on every request,
# and only the isolation proofs use it, explicitly, through transaction.atomic(using="app").
DATABASES["app"]["ATOMIC_REQUESTS"] = False
DATABASES["app"]["TEST"] = {"MIRROR": "default"}
# The superuser URL exists only so tests_production_guard.py can prove the role guard
# refuses a superuser. It is a fixture, not a connection the app ever opens.
TEST_SUPERUSER_DATABASE_URL = env_str(
    "TEST_SUPERUSER_DATABASE_URL",
    "postgres://postgres:postgres-dev-only@localhost:5432/compliance_watch",
)

# (2) The role guard is off for the runner because its default connection is the migrator
#     on purpose (see module docstring). tests_database_role.py runs the guard's function
#     against the `app` alias and against `default` (expecting refusal), and
#     tests_production_guard.py boots subprocesses that keep the guard on.
DB_ROLE_GUARD_ENABLED = False

# (3) MD5 for any legacy hasher Django still loads. There is no auth app and no password
#     (PRD ID-03); this only keeps a stray contrib import from hashing slowly.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# (4) Eager Celery: tasks run inline in the calling transaction so a test sees their
#     effect without a broker. The memory transport keeps the health check's worker ping
#     from touching Redis (tests_health.py patches the ping itself).
CELERY_TASK_ALWAYS_EAGER = True
# An approval in a test must not file the whole real baseline; tests_baseline turns it on.
LIBRARY_BASELINE_ON_APPROVAL_S = 0
# Nor ask a model to translate what it adds; tests_translations turns it on (D-129).
LIBRARY_TRANSLATION_MINUTES = 0
CELERY_BEAT_SCHEDULE.pop("library-translation", None)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"

# (5) Locmem cache: no Redis needed to run the suite, and each test process is isolated.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# (6) Rate limiting off by default, on in the one test that proves it fires (playbook 11.2).
RATE_LIMITING_ENABLED = False

# (7) Throwaway MEDIA_ROOT under the OS temp directory, so a test never writes into the
#     repo and a failed run leaves nothing behind that the next run could read.
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

MEDIA_ROOT = Path(tempfile.gettempdir()) / "compliance-watch-test-media"
STORAGE_BACKEND = "local"

# (8) Mock adapters: no network, no keys, deterministic answers (playbook 16).
LLM_PROVIDER = "mock"
EMBEDDER_PROVIDER = "mock"
AGENT_RUNNER = "mock"
MAIL_PROVIDER = "mock"
REGISTERS_PROVIDER = "mock"

# (9) Stripped middleware: no CORS, no CSP, no HTTPS redirect (tests_middleware.py tests the
#     security middleware directly). Request ID and Server-Timing stay for the audit and
#     timing guards; the access log and scope statement stay because they are behaviour
#     (ACC-08, ACC-07).
MIDDLEWARE = [
    "apps.shared.middleware.RequestIdMiddleware",
    "django.middleware.common.CommonMiddleware",
    # A support session reads its allow-list and nothing else.
    "apps.shared.middleware.SupportReadOnlyMiddleware",
    "apps.governance.access_log.AccessLogMiddleware",
    "apps.shared.agent_access_guard.ScopeStatementMiddleware",
    "apps.shared.middleware.ServerTimingMiddleware",
]
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# (10) DEBUG off so tests exercise the production error paths (no debug pages), with a
#      fixed non-default key so rule 3 of the production-safety block is satisfied.
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# (11) Quiet logs: WARNING and above, still JSON, so a failing test's output is readable.
LOGGING["root"]["level"] = "WARNING"  # type: ignore[index]  # noqa: F405
for _name in ("django", "apps"):
    LOGGING["loggers"][_name]["level"] = "WARNING"  # type: ignore[index]  # noqa: F405

# (12) E2E flag off: the deterministic-code path is tested explicitly by overriding this
#      per test, never by running the whole suite in E2E mode.
E2E_MODE = False

# (12a) The PRD's role matrix (D-136): the suite gives people every system role and proves
#       what each one may not do; the single-role mode is tested by overriding this per test.
TENANT_SINGLE_ROLE = False

# (13) Django's runner with one addition: CI may run one shard of the suite (TEST_SHARD=i/N)
#      so the suite finishes on parallel runners; unset, it is Django's runner unchanged.
TEST_RUNNER = "config.test_runner.ShardingDiscoverRunner"
