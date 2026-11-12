"""Django settings for Compliance Watch.

Every value that varies by environment is read from an environment variable through the
helpers below, which refuse to boot on a value outside the setting's bounds. `.env.example`
at the repo root describes every variable; docs/runbooks/RAILWAY_VARIABLES.md says where
each is set. Dev-only defaults end in `-dev-only` or start `django-insecure-` so the secret
scanner can allowlist them by exact literal (playbook 11.2). The production-safety block at
the end owns the boot guards of playbook 11.1. `RAILWAY_ENVIRONMENT_NAME` is the one
host-specific name, read as the "we are deployed" signal (D-16).
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import dj_database_url
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# --- Environment helpers. Booleans accept 1/true/yes/on, case-insensitively. ---
def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _bounded[N: (int, float)](name: str, value: N, min: N | None, max: N | None) -> N:
    if min is not None and value < min:
        raise ImproperlyConfigured(f"Refusing to boot: {name} is {value}, below its minimum of {min}.")
    if max is not None and value > max:
        raise ImproperlyConfigured(f"Refusing to boot: {name} is {value}, above its maximum of {max}.")
    return value


def env_int(name: str, default: int, min: int | None = None, max: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return _bounded(name, default, min, max)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer, got {raw!r}") from exc
    return _bounded(name, value, min, max)


def env_float(name: str, default: float, min: float | None = None, max: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return _bounded(name, float(default), min, max)
    try:
        value = float(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a number, got {raw!r}") from exc
    if value != value:  # NaN compares false with every bound
        raise ImproperlyConfigured(f"{name} must be a number, got {raw!r}")
    return _bounded(name, value, min, max)


def env_choice(name: str, default: str, choices: tuple[str, ...]) -> str:
    value = os.environ.get(name, default)
    if value not in choices:
        raise ImproperlyConfigured(f"Refusing to boot: {name} is {value!r}, not one of {', '.join(choices)}.")
    return value


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Environment detection (playbook 11.1) ---
# Deny by default: deployed when the host names an environment at all, or when ENVIRONMENT
# is anything but the three non-deployed names. DEBUG never disarms a guard.
NON_DEPLOYED_ENVIRONMENTS = frozenset({"local", "test", "ci"})
ENVIRONMENT = env_str("ENVIRONMENT", "local")
HOST_ENVIRONMENT_NAME = env_str("RAILWAY_ENVIRONMENT_NAME", "")
IS_DEPLOYED_ENVIRONMENT = bool(HOST_ENVIRONMENT_NAME) or ENVIRONMENT not in NON_DEPLOYED_ENVIRONMENTS
# The one deployed name where mock adapters and demo data may run; the UI shows a banner.
MOCKS_ALLOWED_DEPLOYED_ENVIRONMENT = "test"
# Deterministic emailed codes and nothing else; refused deployed here and in the code logic.
E2E_MODE = env_bool("E2E_MODE", False)
# The agent definitions this build ships (AGT-03); only the E2E stack may point elsewhere.
AGENT_DEFINITIONS_DIR = Path(env_str("AGENT_DEFINITIONS_DIR")) if E2E_MODE and env_str("AGENT_DEFINITIONS_DIR") else BASE_DIR / "agents"

DEBUG = env_bool("DEBUG", False)
DEFAULT_INSECURE_SECRET_KEY = "django-insecure-dev-only-change-me"  # noqa: S105 dev-only, allowlisted in .gitleaks.toml
SECRET_KEY = env_str("SECRET_KEY", DEFAULT_INSECURE_SECRET_KEY)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
PRODUCT_NAME = env_str("PRODUCT_NAME", "Compliance Watch")

# --- Application. No django.contrib.auth, sessions or admin (playbook 4.3): nobody has a
# password (tests_no_passwords.py pins the list). `ninja` is listed for its docs templates.
INSTALLED_APPS = [
    "ninja",
    "corsheaders",
    "django.contrib.postgres",  # ArrayField
    "apps.shared",
    "apps.identity",
    "apps.tenants",
    "apps.taxonomy",
    "apps.library",
    "apps.proposals",
    "apps.watch",
    "apps.register",
    "apps.cases",
    "apps.search",
    "apps.home",
    "apps.collab",
    "apps.agents",
    "apps.reports",
    "apps.integrations",
    "apps.governance",
    "apps.billing",
]

MIDDLEWARE = [
    "apps.shared.middleware.RequestIdMiddleware",  # first, so every log line is correlated
    # Outside everything that can answer: a refused body is read to its end before the answer leaves.
    "apps.shared.middleware.UnreadBodyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.shared.middleware.ContentSecurityPolicyMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # A support session reads its allow-list and nothing else.
    "apps.shared.middleware.SupportReadOnlyMiddleware",
    # ACC-08: the access log row of an agent access credential's call.
    "apps.governance.access_log.AccessLogMiddleware",
    # ACC-07: the scope statement on every answer to an agent access credential.
    "apps.shared.agent_access_guard.ScopeStatementMiddleware",
    # A read request reads each vocabulary's labels once.
    "apps.shared.middleware.RequestMemoMiddleware",
    "apps.shared.middleware.ServerTimingMiddleware",  # last: the application's own time
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Database (playbook 14). cw_migrator owns the schema and runs migrations; cw_app runs
# the application with no ownership and no BYPASSRLS. ATOMIC_REQUESTS so `SET LOCAL
# app.tenant_id` lives exactly as long as the request's transaction.
DATABASE_URL = env_str("DATABASE_URL", "postgres://cw_app:cw-app-dev-only@localhost:5432/compliance_watch")
MIGRATOR_DATABASE_URL = env_str(
    "MIGRATOR_DATABASE_URL", "postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/compliance_watch"
)
DATABASE_CONN_MAX_AGE_S = env_int("DATABASE_CONN_MAX_AGE_S", 60, min=0, max=3600)
DATABASES: dict[str, Any] = {
    "default": dj_database_url.parse(DATABASE_URL, conn_max_age=DATABASE_CONN_MAX_AGE_S),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
# JIT off (NFR-02): the RLS subqueries lift a search's estimated cost far above
# `jit_above_cost`, and compiling then dominates the query. Not a setting.
JIT_OFF = {"options": "-c jit=off"}
DATABASES["default"]["OPTIONS"] = {**DATABASES["default"].get("OPTIONS", {}), **JIT_OFF}

# The database role guard (playbook 11.1) runs from SharedConfig.ready(). Commands that run
# as the migrator or need no database are exempt by name. Deliberately not an environment
# variable: a guard an env var can switch off is not a guard (tests_production_guard.py).
DB_ROLE_GUARD_ENABLED = True
DB_ROLE_GUARD_EXEMPT_COMMANDS = frozenset(
    {
        "migrate",
        "makemigrations",
        "showmigrations",
        "sqlmigrate",
        "squashmigrations",
        "migrate_from_zero",
        "seed_reference",
        "seed_e2e",
        "export_openapi",
        "check",
        "test",
    }
)

# --- Cache and Celery (Redis). The health check pings both. ---
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_TIMEZONE = "UTC"
# Keep LOGGING's JSON handler: the worker's own prints exception messages (M2).
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_BEAT_SCHEDULE: dict[str, Any] = {}

# --- No passwords (ID-03): empty, so a stray contrib import inherits nothing. ---
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []
PASSWORD_HASHERS: list[str] = []
AUTHENTICATION_BACKENDS: list[str] = []

# --- Time and language. Storage is always UTC; tenants convert explicitly. ---
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_TZ = True
USE_I18N = False

# --- Transport security (playbook 11.2) ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG and IS_DEPLOYED_ENVIRONMENT
SECURE_HSTS_SECONDS = 0 if DEBUG else env_int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 365, min=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"  # the invitation token rides a URL (F28)
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# The API serves JSON only; the docs page (DEBUG only) gets the relaxed policy.
CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
CONTENT_SECURITY_POLICY_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; "
    "frame-ancestors 'none'; base-uri 'none'"
)
CONTENT_SECURITY_POLICY_DOCS_PREFIXES = ("/api/v1/docs",) if DEBUG else ()

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_CREDENTIALS = True  # the rotating refresh cookie (D-06)
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "if-match",
    "idempotency-key",
    "x-api-key",
    "x-request-id",
    "x-tenant-id",
]
# content-disposition: an evidence download is saved under the name the server chose.
CORS_EXPOSE_HEADERS = ["content-disposition", "etag", "server-timing", "x-request-id"]

# --- Adapters (playbook 16). A mock outside the named test environment refuses to boot. ---
LLM_PROVIDER = env_choice("LLM_PROVIDER", "mock", ("mock", "anthropic", "bedrock"))
ANTHROPIC_API_KEY = env_str("ANTHROPIC_API_KEY", "")
EMBEDDER_PROVIDER = env_choice("EMBEDDER_PROVIDER", "mock", ("mock", "none"))  # a model joins per D-09
EMBEDDING_DIMENSIONS = env_int("EMBEDDING_DIMENSIONS", 1024, min=1, max=16000)  # D-09
# No `managed_agents`: a runner outside the EU (D-54) was never built and is no value at all.
AGENT_RUNNER = env_choice("AGENT_RUNNER", "mock", ("mock", "none"))
RERANKER_PROVIDER = env_choice("RERANKER_PROVIDER", "mock", ("mock", "none"))  # none keeps the fused order
RERANKER_TOP_K = env_int("RERANKER_TOP_K", 50, min=1, max=1000)
MAIL_PROVIDER = env_choice("MAIL_PROVIDER", "mock", ("mock", "smtp", "resend"))
MAIL_FROM = env_str("MAIL_FROM", "no-reply@localhost")
MAIL_SMTP_HOST = env_str("MAIL_SMTP_HOST", "")
MAIL_SMTP_PORT = env_int("MAIL_SMTP_PORT", 587, min=1, max=65535)
MAIL_SMTP_USER = env_str("MAIL_SMTP_USER", "")
MAIL_SMTP_PASSWORD = env_str("MAIL_SMTP_PASSWORD", "")
RESEND_API_KEY = env_str("RESEND_API_KEY", "")  # read only when MAIL_PROVIDER=resend
MAIL_TIMEOUT_SECONDS = env_float("MAIL_TIMEOUT_SECONDS", 8, min=1, max=60)  # a slow code mail is a failed sign-in
MOCK_ADAPTER_SETTINGS = ("LLM_PROVIDER", "EMBEDDER_PROVIDER", "RERANKER_PROVIDER", "AGENT_RUNNER", "MAIL_PROVIDER", "REGISTERS_PROVIDER")

# --- Agents (AGT-03 to AGT-06) ---
AGENT_RESEARCH_TOPIC_MAX_CHARS = env_int("AGENT_RESEARCH_TOPIC_MAX_CHARS", 500, min=1, max=10_000)
AGENT_MIN_CADENCE = env_choice("AGENT_MIN_CADENCE", "weekly", ("daily", "weekly", "monthly"))
AGENTS_PER_TENANT_MAX = env_int("AGENTS_PER_TENANT_MAX", 3, min=0, max=100)
AGENT_DEFAULT_RUN_HOUR = env_int("AGENT_DEFAULT_RUN_HOUR", 6, min=0, max=23)
AGENT_BEAT_INTERVAL_MINUTES = env_int("AGENT_BEAT_INTERVAL_MINUTES", 15, min=1, max=1440)
AGENT_RUNS_PER_BEAT = env_int("AGENT_RUNS_PER_BEAT", 5, min=1, max=1000)
AGENT_RECENT_RUNS = env_int("AGENT_RECENT_RUNS", 5, min=1, max=100)  # a page is at most 100
# The most one run of a bank's own agent may spend, in EUR; stored as the run's budget_limit.
AGENT_RUN_BUDGET_LIMIT = env_str("AGENT_RUN_BUDGET_LIMIT", "5.00")
try:
    _run_budget_limit = Decimal(AGENT_RUN_BUDGET_LIMIT)
except InvalidOperation:
    _run_budget_limit = Decimal(0)
if not (_run_budget_limit.is_finite() and Decimal(0) < _run_budget_limit < Decimal(100_000_000)):
    raise ImproperlyConfigured(f"AGENT_RUN_BUDGET_LIMIT must be an amount in EUR above zero, got {AGENT_RUN_BUDGET_LIMIT!r}")
CELERY_BEAT_SCHEDULE["agents-platform"] = {
    "task": "apps.agents.tasks.run_platform_agents",
    "schedule": AGENT_BEAT_INTERVAL_MINUTES * 60,
}
CELERY_BEAT_SCHEDULE["agents-tenant"] = {
    "task": "apps.agents.tasks.schedule_tenant_agents",
    "schedule": AGENT_BEAT_INTERVAL_MINUTES * 60,
}
# Research requests (AGT-05): per bank per calendar month, then the check_url fetch's limits.
RESEARCH_REQUESTS_PER_MONTH = env_int("RESEARCH_REQUESTS_PER_MONTH", 30, min=1, max=10_000)
RESEARCH_URL_TIMEOUT_SECONDS = env_int("RESEARCH_URL_TIMEOUT_SECONDS", 5, min=1, max=60)
RESEARCH_URL_MAX_BYTES = env_int("RESEARCH_URL_MAX_BYTES", 1_000_000, min=1, max=50_000_000)
RESEARCH_URL_MAX_REDIRECTS = env_int("RESEARCH_URL_MAX_REDIRECTS", 3, min=0, max=10)
RESEARCH_URL_TOTAL_SECONDS = env_int("RESEARCH_URL_TOTAL_SECONDS", 15, min=1, max=300)
RESEARCH_URL_RATE_PER_HOUR = env_int("RESEARCH_URL_RATE_PER_HOUR", 20, min=1, max=1000)  # S-10
SCOPE_RESEARCH_TEXT_MAX_CHARS = env_int("SCOPE_RESEARCH_TEXT_MAX_CHARS", 2000, min=1, max=100_000)

# --- The Anthropic provider (D-07). The key is read from the environment only. ---
LLM_MODEL = env_str("LLM_MODEL", "claude-opus-5")
LLM_MAX_TOKENS = env_int("LLM_MAX_TOKENS", 4096, min=1, max=200_000)
LLM_TIMEOUT_S = env_float("LLM_TIMEOUT_S", 60.0, min=1, max=600)
LLM_MAX_RETRIES = env_int("LLM_MAX_RETRIES", 2, min=0, max=10)
LLM_RETRY_BACKOFF_S = env_float("LLM_RETRY_BACKOFF_S", 0.5, min=0, max=60)
LLM_DEADLINE_S = env_float("LLM_DEADLINE_S", 180.0, min=1, max=3600)
LLM_MAX_RESPONSE_BYTES = env_int("LLM_MAX_RESPONSE_BYTES", 4 * 1024 * 1024, min=1024, max=100 * 1024 * 1024)
LLM_MAX_ERROR_BODY_BYTES = env_int("LLM_MAX_ERROR_BODY_BYTES", 64 * 1024, min=1024, max=1024 * 1024)
# AUD-02, the AI output log: a model's output is stored up to the first; over the second is 422.
AI_GENERATION_OUTPUT_MAX_CHARS = env_int("AI_GENERATION_OUTPUT_MAX_CHARS", 20000, min=1, max=1_000_000)
AI_GENERATION_CITATIONS_MAX = env_int("AI_GENERATION_CITATIONS_MAX", 20, min=1, max=1000)

# --- File storage (playbook 4.6): local for dev and tests, s3 when deployed. ---
STORAGE_BACKEND = env_choice("STORAGE_BACKEND", "local", ("local", "s3"))
MEDIA_ROOT = Path(env_str("STORAGE_LOCAL_ROOT", str(BASE_DIR / "var" / "media")))
STORAGE_S3_ENDPOINT_URL = env_str("STORAGE_S3_ENDPOINT_URL", "")
STORAGE_S3_BUCKET = env_str("STORAGE_S3_BUCKET", "")
STORAGE_S3_REGION = env_str("STORAGE_S3_REGION", "eu-west-1")
STORAGE_S3_ACCESS_KEY_ID = env_str("STORAGE_S3_ACCESS_KEY_ID", "")
STORAGE_S3_SECRET_ACCESS_KEY = env_str("STORAGE_S3_SECRET_ACCESS_KEY", "")

# --- WebAuthn (D-02). The RP ID is the exact app host. ---
WEBAUTHN_RP_ID = env_str("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = PRODUCT_NAME
WEBAUTHN_ORIGINS = env_list("WEBAUTHN_ORIGINS", "http://localhost:3000")
APP_BASE_URL = env_str("APP_BASE_URL", CORS_ALLOWED_ORIGINS[0] if CORS_ALLOWED_ORIGINS else "http://localhost:3000")

# --- Performance budgets and pagination (NFR-02, playbook 10) ---
API_BUDGET_MS = env_int("API_BUDGET_MS", 250, min=1, max=60_000)
SEARCH_BUDGET_MS = env_int("SEARCH_BUDGET_MS", 800, min=1, max=60_000)
SEARCH_RERANKED_BUDGET_MS = env_int("SEARCH_RERANKED_BUDGET_MS", 1500, min=1, max=60_000)
API_PAGE_SIZE_MAX = env_int("API_PAGE_SIZE_MAX", 100, min=1, max=1000)
API_PAGE_SIZE_DEFAULT = env_int("API_PAGE_SIZE_DEFAULT", 20, min=1, max=API_PAGE_SIZE_MAX)
# Below one page nobody reaches a list's second page (H1).
API_PAGE_OFFSET_MAX = env_int("API_PAGE_OFFSET_MAX", 100000, min=API_PAGE_SIZE_MAX, max=10**12)
ASK_FIRST_TOKEN_BUDGET_MS = env_int("ASK_FIRST_TOKEN_BUDGET_MS", 2000, min=1, max=60_000)
PERF_SAMPLES = env_int("PERF_SAMPLES", 20, min=2, max=1000)
PERF_REGRESSION_PCT = env_int("PERF_REGRESSION_PCT", 20, min=1, max=1000)

# --- Search and Ask (SRC-01 to SRC-03) ---
SEARCH_QUERY_MAX_CHARS = env_int("SEARCH_QUERY_MAX_CHARS", 500, min=1, max=10_000)
SEARCH_SIMILAR_MAX_CHARS = env_int("SEARCH_SIMILAR_MAX_CHARS", 8000, min=1, max=100_000)
ASK_QUESTION_MAX_CHARS = env_int("ASK_QUESTION_MAX_CHARS", 2000, min=1, max=20_000)
SEARCH_FEEDBACK_NOTE_MAX_CHARS = env_int("SEARCH_FEEDBACK_NOTE_MAX_CHARS", 2000, min=1, max=20_000)
SEARCH_EMBED_BATCH_SIZE = env_int("SEARCH_EMBED_BATCH_SIZE", 64, min=1, max=2048)
SEARCH_EMBED_SWEEP_INTERVAL_S = env_int("SEARCH_EMBED_SWEEP_INTERVAL_S", 60, min=1, max=86_400)
CELERY_BEAT_SCHEDULE["search-embed-backlog"] = {
    "task": "apps.search.tasks.embed_search_backlog",
    "schedule": SEARCH_EMBED_SWEEP_INTERVAL_S,
}
SEARCH_RRF_K = env_int("SEARCH_RRF_K", 60, min=1, max=1000)
SEARCH_RETRIEVAL_DEPTH = env_int("SEARCH_RETRIEVAL_DEPTH", 50, min=1, max=1000)
SEARCH_CONCEPT_SCORE_FLOOR = env_float("SEARCH_CONCEPT_SCORE_FLOOR", 0.5, min=0, max=1)
SEARCH_SNIPPET_CHARS = env_int("SEARCH_SNIPPET_CHARS", 240, min=1, max=10_000)
# Per caller per minute. No value means "no limit": a limit that can be configured away is not one.
SEARCH_RATE_PER_USER_PER_MINUTE = env_int("SEARCH_RATE_PER_USER_PER_MINUTE", 60, min=1, max=10_000)
ASK_RATE_PER_USER_PER_MINUTE = env_int("ASK_RATE_PER_USER_PER_MINUTE", 10, min=1, max=1000)
# H47, H39, H38: open Ask streams per caller, problem reports per person per hour, visit spacing.
ASK_STREAMS_PER_USER = env_int("ASK_STREAMS_PER_USER", 2, min=1, max=100)
ASK_STREAM_SLOT_TTL_S = int(LLM_DEADLINE_S + LLM_TIMEOUT_S) + 60
PROBLEM_REPORTS_PER_USER_PER_HOUR = env_int("PROBLEM_REPORTS_PER_USER_PER_HOUR", 30, min=1, max=1000)
VISIT_MIN_INTERVAL_SECONDS = env_int("VISIT_MIN_INTERVAL_SECONDS", 60, min=1, max=86_400)
# Each passage is a citation, so the depth may not exceed the AI log's citation cap.
ASK_RETRIEVAL_DEPTH = env_int("ASK_RETRIEVAL_DEPTH", 6, min=1, max=AI_GENERATION_CITATIONS_MAX)
ASK_MAX_TOKENS = env_int("ASK_MAX_TOKENS", 1024, min=1, max=LLM_MAX_TOKENS)

# --- The library (INV-03 to INV-06, PRO-01 to PRO-04, REG-07) ---
# Aligning two versions costs up to the cube of their sentences (H12).
LIBRARY_DIFF_MAX_SENTENCES = env_int("LIBRARY_DIFF_MAX_SENTENCES", 50, min=1, max=200)
LIBRARY_TEXT_MAX_CHARS = env_int("LIBRARY_TEXT_MAX_CHARS", 20000, min=1, max=1_000_000)
LIBRARY_TERM_FILTER_MAX = env_int("LIBRARY_TERM_FILTER_MAX", 20, min=1, max=100)
# The most words an instrument is named in where it is shown; longer gives the compact reference (D-133).
INSTRUMENT_SHORT_NAME_MAX_WORDS = env_int("INSTRUMENT_SHORT_NAME_MAX_WORDS", 3, min=1, max=20)
# The library's own source_url is a URLField of 2000 characters.
PROPOSAL_SOURCE_MAX_CHARS = env_int("PROPOSAL_SOURCE_MAX_CHARS", 2000, min=1, max=2000)
PROPOSAL_SCOPE_MAX_TERMS = env_int("PROPOSAL_SCOPE_MAX_TERMS", 20, min=1, max=100)
PROPOSAL_TEXT_MAX_CHARS = env_int("PROPOSAL_TEXT_MAX_CHARS", 50000, min=1, max=1_000_000)
PROPOSAL_BATCH_MAX_ROWS = env_int("PROPOSAL_BATCH_MAX_ROWS", 100, min=1, max=1000)
RECURRENCE_MAX_OCCURRENCES = env_int("RECURRENCE_MAX_OCCURRENCES", 120, min=1, max=10_000)
LIBRARY_UPDATES_DEFAULT_DAYS = env_int("LIBRARY_UPDATES_DEFAULT_DAYS", 30, min=1, max=3650)
LIBRARY_REPORT_TEXT_MAX_CHARS = env_int("LIBRARY_REPORT_TEXT_MAX_CHARS", 4000, min=1, max=100_000)

# --- The outbox cursor (AUD-01, CAS-01) ---
OUTBOX_BATCH_SIZE = env_int("OUTBOX_BATCH_SIZE", 100, min=1, max=10_000)
OUTBOX_POLL_INTERVAL_S = env_int("OUTBOX_POLL_INTERVAL_S", 10, min=1, max=3600)
OUTBOX_MAX_ATTEMPTS = env_int("OUTBOX_MAX_ATTEMPTS", 5, min=1, max=100)
OUTBOX_RETRY_BACKOFF_S = env_int("OUTBOX_RETRY_BACKOFF_S", 60, min=0, max=86_400)
CELERY_BEAT_SCHEDULE["outbox-deliver"] = {
    "task": "apps.shared.tasks.deliver_outbox",
    "schedule": OUTBOX_POLL_INTERVAL_S,
}

# --- Cases (CAS-01, CAS-04, CAS-05) ---
CASE_CREATION_BATCH = env_int("CASE_CREATION_BATCH", 100, min=1, max=10_000)
CASE_ACTIONS_MAX = env_int("CASE_ACTIONS_MAX", 200, min=1, max=10_000)

# --- The watch (WAT-01, WAT-07, AGT-01) ---
SOURCE_STALE_AFTER_CHECKS = env_int("SOURCE_STALE_AFTER_CHECKS", 1, min=1, max=100)
SOURCE_STALE_GRACE_HOURS = env_int("SOURCE_STALE_GRACE_HOURS", 24, min=0, max=8760)
STANDARDS_PUBLISHER_HOSTS = [
    host.lower()
    for host in env_list(
        "STANDARDS_PUBLISHER_HOSTS", "iso.org,iec.ch,sis.se,ds.dk,standard.no,sfs.fi,pcisecuritystandards.org"
    )
]
WATCH_RUN_MAX_PROPOSALS = env_int("WATCH_RUN_MAX_PROPOSALS", 50, min=1, max=10_000)
WATCH_RUN_MAX_CHANGES = env_int("WATCH_RUN_MAX_CHANGES", 50, min=1, max=10_000)
WATCH_RUN_MAX_RECHECKS = env_int("WATCH_RUN_MAX_RECHECKS", 100, min=1, max=10_000)

# --- The library baseline and translations (D-118, D-129); 0 switches each off. ---
LIBRARY_BASELINE_FILING_MINUTES = env_int("LIBRARY_BASELINE_FILING_MINUTES", 0 if E2E_MODE else 60, min=0, max=10_080)
if LIBRARY_BASELINE_FILING_MINUTES:
    CELERY_BEAT_SCHEDULE["library-baseline"] = {
        "task": "apps.proposals.tasks.file_library_baseline",
        "schedule": LIBRARY_BASELINE_FILING_MINUTES * 60,
    }
LIBRARY_BASELINE_ON_APPROVAL_S = env_int("LIBRARY_BASELINE_ON_APPROVAL_S", 0 if E2E_MODE else 10, min=0, max=3600)
LIBRARY_TRANSLATION_MINUTES = env_int("LIBRARY_TRANSLATION_MINUTES", 0 if E2E_MODE else 10, min=0, max=10_080)
LIBRARY_TRANSLATION_RUN_MAX = env_int("LIBRARY_TRANSLATION_RUN_MAX", 100, min=1, max=10_000)
LIBRARY_TRANSLATION_TEXT_MAX_CHARS = env_int("LIBRARY_TRANSLATION_TEXT_MAX_CHARS", 8000, min=1, max=PROPOSAL_TEXT_MAX_CHARS)
LIBRARY_TRANSLATION_MAX_FAILURES = env_int("LIBRARY_TRANSLATION_MAX_FAILURES", 3, min=1, max=100)  # S-9
if LIBRARY_TRANSLATION_MINUTES:
    CELERY_BEAT_SCHEDULE["library-translation"] = {
        "task": "apps.proposals.tasks.file_library_translations",
        "schedule": LIBRARY_TRANSLATION_MINUTES * 60,
    }
# Approve all (D-128): how long progress stays readable, and when a silent run is stopped.
PROPOSALS_APPROVE_ALL_KEEP_S = env_int("PROPOSALS_APPROVE_ALL_KEEP_S", 86_400, min=60, max=30 * 86_400)
PROPOSALS_APPROVE_ALL_STALE_S = env_int("PROPOSALS_APPROVE_ALL_STALE_S", 300, min=30, max=86_400)

# --- Home, briefing, reminders and the workflow policy (HOM-01, HOM-02, COL-02) ---
HOME_COMING_UP_ITEMS = env_int("HOME_COMING_UP_ITEMS", 5, min=1, max=50)
BRIEFING_SEND_WEEKDAY = env_int("BRIEFING_SEND_WEEKDAY", 0, min=0, max=6)  # Monday is 0
BRIEFING_SEND_HOUR = env_int("BRIEFING_SEND_HOUR", 7, min=0, max=23)  # the bank's local hour
BRIEFING_MAX_ITEMS = env_int("BRIEFING_MAX_ITEMS", 10, min=1, max=100)
CELERY_BEAT_SCHEDULE["briefing-weekly"] = {
    "task": "apps.home.tasks.send_weekly_briefings",
    "schedule": crontab(minute="0"),
}
REMINDER_SEND_HOUR = env_int("REMINDER_SEND_HOUR", 7, min=0, max=23)
CELERY_BEAT_SCHEDULE["collab-reminders"] = {
    "task": "apps.collab.tasks.send_reminders",
    "schedule": crontab(minute="0"),
}
# What a new bank's workflow policy starts at; the bounds are the tenant table's checks.
WORKFLOW_REMINDER_DAYS_BEFORE = [int(value) for value in env_list("WORKFLOW_REMINDER_DAYS_BEFORE", "3")]
WORKFLOW_REVIEW_REMINDER_DAYS_BEFORE = [int(value) for value in env_list("WORKFLOW_REVIEW_REMINDER_DAYS_BEFORE", "30")]
WORKFLOW_ESCALATE_AFTER_DAYS = env_int("WORKFLOW_ESCALATE_AFTER_DAYS", 5, min=1, max=90)
WORKFLOW_ESCALATE_TO_ROLE = env_str("WORKFLOW_ESCALATE_TO_ROLE", "compliance_officer")
WORKFLOW_DIGEST_WEEKDAY = env_choice(
    "WORKFLOW_DIGEST_WEEKDAY", "monday", ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
)
WORKFLOW_TRIAGE_TARGET_HOURS = env_int("WORKFLOW_TRIAGE_TARGET_HOURS", 48, min=1, max=720)

# --- Calendar subscriptions and participants (HOM-04, COL-04) ---
CALENDAR_FEEDS_PER_USER = env_int("CALENDAR_FEEDS_PER_USER", 5, min=1, max=100)
CALENDAR_FEED_IDLE_DAYS = env_int("CALENDAR_FEED_IDLE_DAYS", 30, min=1, max=3650)
CALENDAR_FEED_REVOKED_SHOWN = env_int("CALENDAR_FEED_REVOKED_SHOWN", 5, min=0, max=100)
CALENDAR_FEED_RATE_PER_MINUTE = env_int("CALENDAR_FEED_RATE_PER_MINUTE", 20, min=1, max=1000)
CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS = env_int("CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS", 300, min=0, max=86_400)
MAX_PARTICIPANTS_PER_RECORD = env_int("MAX_PARTICIPANTS_PER_RECORD", 50, min=1, max=1000)

# --- The malware scanner (CAS-05, D-101). A failed or timed-out scan is never clean. ---
SCANNER_PROVIDER = env_choice("SCANNER_PROVIDER", "mock", ("mock", "clamd"))
SCANNER_HOST = env_str("SCANNER_HOST", "localhost")
SCANNER_PORT = env_int("SCANNER_PORT", 3310, min=1, max=65535)
SCANNER_TIMEOUT_SECONDS = env_float("SCANNER_TIMEOUT_SECONDS", 60.0, min=1, max=3600)

# --- Public registers (TEN-07, TEN-08, FP-05). `live` when deployed, `mock` elsewhere. ---
REGISTERS_PROVIDER = env_choice("REGISTERS_PROVIDER", "live" if IS_DEPLOYED_ENVIRONMENT else "mock", ("live", "mock"))
REGISTERS_GLEIF_URL = env_str("REGISTERS_GLEIF_URL", "https://api.gleif.org/api/v1")
REGISTERS_FI_URL = env_str("REGISTERS_FI_URL", "https://www.fi.se/sv/vara-register/foretagsregistret")
REGISTERS_EBA_URL = env_str("REGISTERS_EBA_URL", "https://euclid.eba.europa.eu/register")  # D-126
if not all(url.startswith("https://") for url in (REGISTERS_GLEIF_URL, REGISTERS_FI_URL, REGISTERS_EBA_URL)):
    raise ImproperlyConfigured("REGISTERS_GLEIF_URL, REGISTERS_FI_URL and REGISTERS_EBA_URL must be https addresses")
REGISTERS_TIMEOUT_SECONDS = env_int("REGISTERS_TIMEOUT_SECONDS", 10, min=1, max=120)
REGISTERS_MAX_BYTES = env_int("REGISTERS_MAX_BYTES", 2_000_000, min=10_000, max=50_000_000)
REGISTERS_MAX_ENTITIES = env_int("REGISTERS_MAX_ENTITIES", 100, min=1, max=500)
REGISTERS_MAX_BRANCHES = env_int("REGISTERS_MAX_BRANCHES", 40, min=0, max=200)
REGISTERS_RECHECK_HOUR = env_int("REGISTERS_RECHECK_HOUR", 3, min=0, max=23)  # UTC
REGISTERS_JOB_SECONDS = env_int("REGISTERS_JOB_SECONDS", 300, min=30, max=3600)
REGISTERS_LOOKUPS_PER_HOUR = env_int("REGISTERS_LOOKUPS_PER_HOUR", 10, min=1, max=100)  # S-11
CELERY_BEAT_SCHEDULE["registers-recheck"] = {
    "task": "apps.tenants.tasks.recheck_registers",
    "schedule": crontab(minute="17", hour=str(REGISTERS_RECHECK_HOUR)),
}

# --- Evidence, tagging, exports, the register, My work and comments ---
EVIDENCE_ALLOWED_TYPES = env_list(
    "EVIDENCE_ALLOWED_TYPES",
    "application/pdf,"
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
    "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
    "image/png,image/jpeg,text/plain,text/csv",
)
EVIDENCE_MAX_BYTES = env_int("EVIDENCE_MAX_BYTES", 25 * 1024 * 1024, min=1, max=512 * 1024 * 1024)
# The largest request body the API reads to its end when a view answered without reading it
# (apps.shared.middleware.UnreadBodyMiddleware). The web server passes on nothing above its
# own limit, 26 MiB (frontend API_INTERNAL_MAX_BODY_BYTES), so this covers every call that
# comes through it; a larger body is left unread.
UNREAD_BODY_MAX_BYTES = env_int("UNREAD_BODY_MAX_BYTES", 26 * 1024 * 1024, min=0, max=512 * 1024 * 1024)
EVIDENCE_SCAN_RETRIES = env_int("EVIDENCE_SCAN_RETRIES", 2, min=0, max=10)
CASE_EVIDENCE_MAX = env_int("CASE_EVIDENCE_MAX", 200, min=1, max=10_000)
BULK_TAGGING_MAX_RECORDS = env_int("BULK_TAGGING_MAX_RECORDS", 200, min=1, max=10_000)
EXPORT_RETENTION_DAYS = env_int("EXPORT_RETENTION_DAYS", 7, min=1, max=365)
REGISTER_BULK_MAX = env_int("REGISTER_BULK_MAX", 100, min=1, max=1000)
MY_WORK_DUE_SOON_DAYS = env_int("MY_WORK_DUE_SOON_DAYS", 30, min=1, max=365)
MY_WORK_AWARE_DAYS = env_int("MY_WORK_AWARE_DAYS", 14, min=1, max=365)
COMMENT_MAX_CHARS = env_int("COMMENT_MAX_CHARS", 4000, min=1, max=100_000)
COMMENT_EDIT_MINUTES = env_int("COMMENT_EDIT_MINUTES", 15, min=0, max=1440)  # also My work's `canEdit`
TENANT_LIST_MAX_ROWS = env_int("TENANT_LIST_MAX_ROWS", 500, min=1, max=100_000)  # H32

# --- The weekly digest (COL-02): My work's page is at most 100. ---
DIGEST_MAX_ITEMS = env_int("DIGEST_MAX_ITEMS", 20, min=1, max=100)
DIGEST_SEND_HOUR = env_int("DIGEST_SEND_HOUR", 7, min=0, max=23)
CELERY_BEAT_SCHEDULE["collab-digests"] = {
    "task": "apps.collab.tasks.send_digests",
    "schedule": crontab(minute="0"),
}

# --- Health check (playbook 2.2) ---
HEALTH_WORKER_PING_TIMEOUT_S = env_float("HEALTH_WORKER_PING_TIMEOUT_S", 1.0, min=0.1, max=30)
HEALTH_WORKER_PING_LIMIT = 1  # one reply, so a large fleet never makes /health/ slow
HEALTH_CACHE_SECONDS = env_float("HEALTH_CACHE_SECONDS", 5, min=0, max=60)  # L-8

# --- Enrolment, invitations and sign-in (ID-01 to ID-03, playbook 4.2) ---
INVITATION_TTL_HOURS = env_int("INVITATION_TTL_HOURS", 72, min=1, max=720)
ENROLMENT_CODE_DIGITS = env_int("ENROLMENT_CODE_DIGITS", 6, min=6, max=10)
ENROLMENT_CODE_TTL_MINUTES = env_int("ENROLMENT_CODE_TTL_MINUTES", 10, min=1, max=60)
ENROLMENT_CODE_MAX_ATTEMPTS = env_int("ENROLMENT_CODE_MAX_ATTEMPTS", 5, min=1, max=10)
ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR = env_int("ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR", 5, min=1, max=100)
ENROLMENT_CODE_RATE_PER_IP_PER_HOUR = env_int("ENROLMENT_CODE_RATE_PER_IP_PER_HOUR", 20, min=1, max=1000)
# Every other auth ceremony endpoint (verify code, passkey sign-in, refresh), per IP.
AUTH_RATE_PER_IP_PER_MINUTE = env_int("AUTH_RATE_PER_IP_PER_MINUTE", 30, min=1, max=1000)
# Proxies of ours appending to X-Forwarded-For; 0 trusts the socket address (rule 11).
TRUSTED_PROXY_HOPS = env_int("TRUSTED_PROXY_HOPS", 1 if IS_DEPLOYED_ENVIRONMENT else 0, min=0, max=5)
CHALLENGE_TTL_SECONDS = env_int("CHALLENGE_TTL_SECONDS", 120, min=10, max=600)  # a WebAuthn challenge
# The one code E2E journeys type, read only under E2E_MODE (refused deployed, rule 4).
E2E_FIXED_CODE = "123456"

# --- Sessions, step-up and keys (ID-06 to ID-10, D-06) ---
ACCESS_TOKEN_TTL_MINUTES = env_int("ACCESS_TOKEN_TTL_MINUTES", 10, min=1, max=60)
SESSION_IDLE_MINUTES_MAX = env_int("SESSION_IDLE_MINUTES_MAX", 8 * 60, min=1, max=1440)
SESSION_ABSOLUTE_HOURS_MAX = env_int("SESSION_ABSOLUTE_HOURS_MAX", 24, min=1, max=168)
# A session refreshes only when its token runs out, so the idle floor must outlast the token.
SESSION_IDLE_MINUTES_MIN = env_int(
    "SESSION_IDLE_MINUTES_MIN", 15, min=ACCESS_TOKEN_TTL_MINUTES + 1, max=SESSION_IDLE_MINUTES_MAX
)
SESSION_IDLE_MINUTES_DEFAULT = env_int(
    "SESSION_IDLE_MINUTES_DEFAULT", 30, min=SESSION_IDLE_MINUTES_MIN, max=SESSION_IDLE_MINUTES_MAX
)
SESSION_ABSOLUTE_HOURS_DEFAULT = env_int("SESSION_ABSOLUTE_HOURS_DEFAULT", 12, min=1, max=SESSION_ABSOLUTE_HOURS_MAX)
REFRESH_REPLAY_GRACE_SECONDS = env_int("REFRESH_REPLAY_GRACE_SECONDS", 30, min=0, max=300)
STEP_UP_FRESHNESS_MINUTES = env_int("STEP_UP_FRESHNESS_MINUTES", 5, min=1, max=15)
# The rotating refresh cookie (ADR 0006): HttpOnly, SameSite=Strict, scoped to the auth path.
REFRESH_COOKIE_NAME = "cw_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_SECURE = not DEBUG
API_KEY_LAST_USED_THROTTLE_SECONDS = env_int("API_KEY_LAST_USED_THROTTLE_SECONDS", 60, min=0, max=3600)
# Agent access credentials (ACC-03, ACC-09): the longest life of a key and a personal token.
AGENT_ACCESS_KEY_MAX_DAYS = env_int("AGENT_ACCESS_KEY_MAX_DAYS", 90, min=1, max=365)
PERSONAL_TOKEN_MAX_DAYS = env_int("PERSONAL_TOKEN_MAX_DAYS", 90, min=1, max=365)
AGENT_ACCESS_RATE_PER_MINUTE = env_int("AGENT_ACCESS_RATE_PER_MINUTE", 60, min=1, max=10_000)
# Support access (TEN-06, D-49): the longest window, and how long an undecided request lives.
SUPPORT_ACCESS_MAX_HOURS = env_int("SUPPORT_ACCESS_MAX_HOURS", 4, min=1, max=72)
SUPPORT_ACCESS_REQUEST_TTL_HOURS = env_int("SUPPORT_ACCESS_REQUEST_TTL_HOURS", 24, min=1, max=168)

# --- Scope items, what applies and the regulatory scope request (OWN-01, ACC-06, FP-02) ---
SCOPE_ITEM_DESCRIPTION_MAX_CHARS = env_int("SCOPE_ITEM_DESCRIPTION_MAX_CHARS", 2000, min=1, max=100_000)
AGENT_ACCESS_DESCRIPTION_MAX_CHARS = env_int("AGENT_ACCESS_DESCRIPTION_MAX_CHARS", 2000, min=1, max=100_000)
AGENT_ACCESS_NOTE_MATCH_WORDS = env_int("AGENT_ACCESS_NOTE_MATCH_WORDS", 2, min=1, max=20)
WHAT_APPLIES_SUMMARY_DEADLINE_MS = env_int("WHAT_APPLIES_SUMMARY_DEADLINE_MS", 2000, min=1, max=60_000)
WHAT_APPLIES_SUMMARY_FACTS = env_int("WHAT_APPLIES_SUMMARY_FACTS", 20, min=1, max=1000)
WHAT_APPLIES_SUMMARY_MAX_TOKENS = env_int("WHAT_APPLIES_SUMMARY_MAX_TOKENS", 400, min=1, max=LLM_MAX_TOKENS)
# A model call's list price in minor units per million tokens (Verification_Log).
LLM_PRICE_INPUT_MINOR_PER_MTOK = env_int("LLM_PRICE_INPUT_MINOR_PER_MTOK", 500, min=0)
LLM_PRICE_OUTPUT_MINOR_PER_MTOK = env_int("LLM_PRICE_OUTPUT_MINOR_PER_MTOK", 2500, min=0)
# D-125: a bank's only approver may approve their own scope request, with a passkey, marked
# `sole_approver` and audited. False restores four eyes everywhere.
FOOTPRINT_SOLE_APPROVER_ALLOWED = env_bool("FOOTPRINT_SOLE_APPROVER_ALLOWED", True)
FOOTPRINT_CHANGE_MAX_TERMS = env_int("FOOTPRINT_CHANGE_MAX_TERMS", 50, min=1, max=1000)
FOOTPRINT_ENTITY_CHANGE_MAX = env_int("FOOTPRINT_ENTITY_CHANGE_MAX", 200, min=1, max=10_000)

# --- Rate limiting (playbook 11.2). Off in tests (test_settings override 6). ---
RATE_LIMITING_ENABLED = env_bool("RATE_LIMITING_ENABLED", True)

# --- Logging (playbook 4.7): JSON with the request id; never tenant content. ---
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.shared.middleware.RequestIdLogFilter"}},
    "formatters": {"json": {"()": "apps.shared.logging.JsonFormatter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json", "filters": ["request_id"]}
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Its DEBUG lines carry an Ask event's repr, the reader's question (AskPrivacyTests).
        "django.template": {"level": "INFO"},
    },
}

# --- Sentry (playbook 11.2), only when SENTRY_DSN is set. No PII, bodies or locals; both
# scrubbers, because transactions bypass before_send. ---
SENTRY_DSN = env_str("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1, min=0, max=1)
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import ignore_logger
    from sentry_sdk.integrations.stdlib import StdlibIntegration

    from apps.shared.sentry_scrub import before_send, before_send_transaction

    # A gunicorn access line as a breadcrumb would ride on the next event, whoever's it is.
    ignore_logger("gunicorn.access")
    # The stdlib integration names spans after outbound URLs and propagation sends the public
    # key to every host fetched; Sentry needs neither (S-8).
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=HOST_ENVIRONMENT_NAME or ENVIRONMENT,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        disabled_integrations=[StdlibIntegration],
        trace_propagation_targets=[],
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        before_send=before_send,
        before_send_transaction=before_send_transaction,
    )

# --- Production-safety block (playbook 11.1) ---
# apps/shared/tests_production_guard.py boots Django under `prod`, `Production`, `demo`,
# `dev`, `local`, `test` and `ci` to prove every branch.
#
#  1. Deployed is the default. Only `local`, `test` and `ci` without a host environment
#     name are non-deployed; anything else, and any RAILWAY_ENVIRONMENT_NAME, is deployed.
#  2. DEBUG on a deployed environment leaks settings, SQL and stack traces to the browser.
#  3. The default SECRET_KEY signs nothing safely; tolerated only on the non-deployed names.
#  4. E2E_MODE makes the enrolment code deterministic: catastrophic anywhere reachable from
#     the internet (PRD ID-02, ID-03).
#  5. A mock LLM, embedder, agent runner, mailer or register reader on a deployed
#     environment other than `test` means silent no-ops. `test` may run mocks with a banner.
#  6. The local file backend is a container's ephemeral disk; deployed uses s3.
#  7. The database role: checked at boot on the live connection by
#     apps.shared.db_role_guard from SharedConfig.ready(); settings open no connection.
#  8. The WebAuthn RP ID is the exact app host (ADR 0002); `localhost` deployed enrols
#     passkeys nobody can use.
#  9. RATE_LIMITING_ENABLED=false switches every bucket off at once; laptops and tests only
#     (M2). Each bucket's own size already refuses to boot below 1.
# 10. Processors outside the EU (D-54, ADR 0047). On every deployed environment but `test`,
#     the `anthropic` provider is refused, and Sentry only on a host ending
#     `.ingest.de.sentry.io`. The lists are code, never variables. The `managed_agents`
#     runner is refused everywhere: AGENT_RUNNER names no such value.
# 11. TRUSTED_PROXY_HOPS=0 behind the edge keys every per-IP limit and security log row on
#     the proxy's address. A deployed environment defaults to 1 and refuses 0 (L-18).
def _refuse(reason: str) -> None:
    raise ImproperlyConfigured(f"Refusing to boot: {reason}")


if IS_DEPLOYED_ENVIRONMENT and DEBUG:
    _refuse(
        f"DEBUG=True on deployed environment {ENVIRONMENT!r} "
        f"(host name {HOST_ENVIRONMENT_NAME!r}). Rule 2 of the production-safety block."
    )
if IS_DEPLOYED_ENVIRONMENT and (not SECRET_KEY or SECRET_KEY == DEFAULT_INSECURE_SECRET_KEY):
    _refuse(
        f"SECRET_KEY is missing or the dev-only default on deployed environment "
        f"{ENVIRONMENT!r}. Rule 3. Set SECRET_KEY in the host's variables."
    )
if IS_DEPLOYED_ENVIRONMENT and E2E_MODE:
    _refuse(f"E2E_MODE is set on deployed environment {ENVIRONMENT!r}. Rule 4.")
if IS_DEPLOYED_ENVIRONMENT and ENVIRONMENT != MOCKS_ALLOWED_DEPLOYED_ENVIRONMENT:
    _mocked = [name for name in MOCK_ADAPTER_SETTINGS if globals()[name] == "mock"]
    if _mocked:
        _refuse(
            f"mock adapter(s) {', '.join(_mocked)} on deployed environment "
            f"{ENVIRONMENT!r}. Only ENVIRONMENT={MOCKS_ALLOWED_DEPLOYED_ENVIRONMENT!r} "
            "may run a mock. Rule 5."
        )
if IS_DEPLOYED_ENVIRONMENT and MAIL_PROVIDER == "resend" and not RESEND_API_KEY:
    _refuse(f"MAIL_PROVIDER=resend with no RESEND_API_KEY on deployed environment {ENVIRONMENT!r}.")
if IS_DEPLOYED_ENVIRONMENT and STORAGE_BACKEND == "local":
    _refuse(f"STORAGE_BACKEND=local on deployed environment {ENVIRONMENT!r}. Rule 6.")
if IS_DEPLOYED_ENVIRONMENT and (
    WEBAUTHN_RP_ID in {"", "localhost"} or any("localhost" in origin for origin in WEBAUTHN_ORIGINS)
):
    _refuse(
        f"WEBAUTHN_RP_ID={WEBAUTHN_RP_ID!r} / WEBAUTHN_ORIGINS={WEBAUTHN_ORIGINS!r} on deployed "
        f"environment {ENVIRONMENT!r}. Rule 8: set both to the app host (ADR 0002)."
    )
if IS_DEPLOYED_ENVIRONMENT and not RATE_LIMITING_ENABLED:
    _refuse(f"RATE_LIMITING_ENABLED=false on deployed environment {ENVIRONMENT!r}. Rule 9.")
if IS_DEPLOYED_ENVIRONMENT and ENVIRONMENT != MOCKS_ALLOWED_DEPLOYED_ENVIRONMENT:
    if LLM_PROVIDER == "anthropic":
        _refuse(f"LLM_PROVIDER='anthropic' on deployed environment {ENVIRONMENT!r}: it processes outside the EU. Rule 10 (D-54).")
    if SENTRY_DSN and not (urlsplit(SENTRY_DSN).hostname or "").endswith(".ingest.de.sentry.io"):
        _refuse(f"SENTRY_DSN is not on ingest.de.sentry.io on deployed environment {ENVIRONMENT!r}. Rule 10 (D-54).")
if IS_DEPLOYED_ENVIRONMENT and TRUSTED_PROXY_HOPS < 1:
    _refuse(f"TRUSTED_PROXY_HOPS={TRUSTED_PROXY_HOPS} on deployed environment {ENVIRONMENT!r}. Rule 11: set 1 behind Railway's edge.")

logging.getLogger(__name__).debug(
    "settings loaded", extra={"environment": ENVIRONMENT, "deployed": IS_DEPLOYED_ENVIRONMENT}
)
