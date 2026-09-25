"""Test settings (playbook 2.2): import everything, then override. Every override carries a
numbered comment saying why. Tests run on PostgreSQL with pgvector, never SQLite.

Two database aliases:

- `default` connects as cw_migrator. Django's test runner creates and drops the throwaway
  database `test_compliance_watch`, which needs CREATEDB (granted to cw_migrator by
  infra/db/init.sql) and table ownership for migrations. So the runner's own connection
  is the schema owner, by design.
- `app` connects as cw_app to the same throwaway database (TEST.MIRROR points it at
  default's test database). Tests that must prove isolation or the role guard open this
  alias: `connections["app"]` sees the tables the way production does, with row-level
  security forced and no ownership. A test that uses it declares
  `databases = {"default", "app"}`. Rows written inside a TestCase transaction on
  `default` are invisible on `app` (different connection); use TransactionTestCase when
  the proof needs committed rows.
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
from config.settings import DATABASE_URL, MIGRATOR_DATABASE_URL, env_str  # noqa: E402

# (1) The runner creates the throwaway database as cw_migrator (CREATEDB, owns tables).
#     `app` mirrors it as cw_app so the RLS and role guards test the production role.
DATABASES = {
    "default": dj_database_url.parse(MIGRATOR_DATABASE_URL, conn_max_age=0),  # noqa: F405
    "app": dj_database_url.parse(DATABASE_URL, conn_max_age=0),  # noqa: F405
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
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
#     (PRD ID-03); this only keeps a stray contrib import from spending 300 ms per hash.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# (4) Eager Celery: tasks run inline in the calling transaction so a test sees their
#     effect without a broker. The memory transport keeps the health check's worker ping
#     from touching Redis (tests_health.py patches the ping itself).
CELERY_TASK_ALWAYS_EAGER = True
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

# (9) Stripped middleware: no CORS, no CSP, no HTTPS redirect. The security middleware is
#     unit-tested directly in tests_middleware.py; the request ID and Server-Timing
#     middleware stay because the audit and timing guards read their headers.
MIDDLEWARE = [
    "apps.shared.middleware.RequestIdMiddleware",
    "django.middleware.common.CommonMiddleware",
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

# (13) Django's runner with one addition: CI may run one shard of the suite (TEST_SHARD=i/N)
#      so the suite finishes on parallel runners; unset, it is Django's runner unchanged.
TEST_RUNNER = "config.test_runner.ShardingDiscoverRunner"
