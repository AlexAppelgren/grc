"""Django settings for Compliance Watch.

Read top to bottom: environment detection, the application, the database and its two
roles, adapters, every threshold under a banner naming its requirement, logging, Sentry,
and last the production-safety block that owns the boot guards of playbook 11.1.

Every value that varies by environment is read from an environment variable. Dev-only
defaults are literals ending in `-dev-only` or starting `django-insecure-` so the secret
scanner can allowlist them by exact literal (playbook 11.2). `.env.example` at the repo
root lists every variable with a comment.

Nothing in here is Railway-specific beyond reading `RAILWAY_ENVIRONMENT_NAME` as the
"we are deployed" signal (DECISIONS D-16).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------------------
# Environment helpers. Booleans accept 1/true/yes/on, case-insensitively, nothing else.
# ---------------------------------------------------------------------------------------
def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer, got {raw!r}") from exc


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------------------
# Environment detection (playbook 11.1). Deny by default: the environment is "deployed"
# when the host names it at all, or when ENVIRONMENT is anything other than the three
# non-deployed names. `prod`, `Production`, `demo` and `dev` are all deployed. DEBUG never
# disarms a guard.
# ---------------------------------------------------------------------------------------
NON_DEPLOYED_ENVIRONMENTS = frozenset({"local", "test", "ci"})
ENVIRONMENT = env_str("ENVIRONMENT", "local")
HOST_ENVIRONMENT_NAME = env_str("RAILWAY_ENVIRONMENT_NAME", "")
IS_DEPLOYED_ENVIRONMENT = bool(HOST_ENVIRONMENT_NAME) or ENVIRONMENT not in NON_DEPLOYED_ENVIRONMENTS
# The one deployed name where mock adapters and demo data may run (RAILWAY_DEPLOY.md). The
# UI shows a banner while a mock is active.
MOCKS_ALLOWED_DEPLOYED_ENVIRONMENT = "test"
# The E2E flag makes emailed codes deterministic and unlocks nothing else. Refused when
# deployed on two independent legs: here at boot and again in the code-issuing logic.
E2E_MODE = env_bool("E2E_MODE", False)

DEBUG = env_bool("DEBUG", False)
DEFAULT_INSECURE_SECRET_KEY = "django-insecure-dev-only-change-me"  # noqa: S105 dev-only, allowlisted in .gitleaks.toml
SECRET_KEY = env_str("SECRET_KEY", DEFAULT_INSECURE_SECRET_KEY)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

PRODUCT_NAME = env_str("PRODUCT_NAME", "Compliance Watch")

# ---------------------------------------------------------------------------------------
# Application. No django.contrib.auth, no sessions, no admin (playbook 4.3): nobody has a
# password and the API with its permissions is the only write surface. `ninja` is listed
# for its docs templates only.
# ---------------------------------------------------------------------------------------
INSTALLED_APPS = [
    "ninja",
    "corsheaders",
    # For ArrayField (role permissions, key scopes, credential transports). No auth, no
    # sessions, no admin: nobody has a password (tests_no_passwords.py pins the list).
    "django.contrib.postgres",
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
    # Request ID first so every later log line, including the security middleware's, is
    # correlated (playbook 4.7).
    "apps.shared.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.shared.middleware.ContentSecurityPolicyMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Timing last so the measurement is the application's own time (playbook 10), not
    # the middleware stack above it.
    "apps.shared.middleware.ServerTimingMiddleware",
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

# ---------------------------------------------------------------------------------------
# Database (playbook 14). Two roles: cw_migrator owns the schema and runs migrations;
# cw_app runs the application with no ownership and no BYPASSRLS. DATABASE_URL is the app
# role. MIGRATOR_DATABASE_URL is used by docker-entrypoint.sh, migrate_from_zero and the
# test runner (config/test_settings.py, override 1). ATOMIC_REQUESTS so `SET LOCAL
# app.tenant_id` lives exactly as long as the request's transaction.
# ---------------------------------------------------------------------------------------
DATABASE_URL = env_str(
    "DATABASE_URL", "postgres://cw_app:cw-app-dev-only@localhost:5432/compliance_watch"
)
MIGRATOR_DATABASE_URL = env_str(
    "MIGRATOR_DATABASE_URL",
    "postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/compliance_watch",
)
# Persistent connections pair with single-region deploys (playbook 10).
DATABASE_CONN_MAX_AGE_S = env_int("DATABASE_CONN_MAX_AGE_S", 60)
DATABASES: dict[str, Any] = {
    "default": dj_database_url.parse(DATABASE_URL, conn_max_age=DATABASE_CONN_MAX_AGE_S),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# The boot guard for the database role (playbook 11.1, AC-NFR2) runs from
# apps.shared.apps.SharedConfig.ready() through apps.shared.db_role_guard. Commands that
# legitimately run as the migrator, or need no database, are exempt by name. Everything
# else (gunicorn, celery, runserver, shell) is checked. The test runner disables the guard
# in test_settings because its default connection is the migrator by design, and
# tests_database_role.py proves the guard against the `app` alias instead. Deliberately
# not an environment variable: a guard that an env var can switch off is not a guard
# (tests_production_guard.py proves DB_ROLE_GUARD_ENABLED=false in the environment does
# nothing).
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

# ---------------------------------------------------------------------------------------
# Cache and Celery (Redis). The health check pings both.
# ---------------------------------------------------------------------------------------
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
CELERY_BROKER_URL = REDIS_URL
# `crontab` is pure Celery and pulls in no Django app, so a beat entry further down this
# file can name a time of day rather than only an interval in seconds.
from celery.schedules import crontab  # noqa: E402 settings is read top to bottom, not imported as a package

CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE: dict[str, Any] = {}

# ---------------------------------------------------------------------------------------
# No passwords (PRD ID-03, playbook 4.2). There is no auth app to configure; these are set
# to their empty values so a later `django.contrib.auth` import cannot quietly inherit
# Django's defaults. apps/shared/tests_no_passwords.py pins all three.
# ---------------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []
PASSWORD_HASHERS: list[str] = []
AUTHENTICATION_BACKENDS: list[str] = []

# ---------------------------------------------------------------------------------------
# Time and language. Storage is always UTC (playbook 4.3); tenants convert explicitly.
# Content languages and jurisdictions are data (playbook 17), not settings.
# ---------------------------------------------------------------------------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_TZ = True
USE_I18N = False
DEFAULT_TENANT_TIMEZONE = "Europe/Stockholm"

# ---------------------------------------------------------------------------------------
# Transport security (playbook 11.2). HSTS and secure cookies whenever not DEBUG, frames
# denied, a strict CSP from apps.shared.middleware, CORS allowlist scoped to /api/.
# ---------------------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG and IS_DEPLOYED_ENVIRONMENT
SECURE_HSTS_SECONDS = 0 if DEBUG else env_int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"  # the invitation token rides a URL (F28)
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
# The API serves JSON only, so nothing may load or embed it. The docs page (DEBUG only)
# gets the relaxed policy for the paths below.
CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
CONTENT_SECURITY_POLICY_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; "
    "frame-ancestors 'none'; base-uri 'none'"
)
CONTENT_SECURITY_POLICY_DOCS_PREFIXES = ("/api/v1/docs",) if DEBUG else ()

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_CREDENTIALS = True  # the rotating refresh cookie (DECISIONS D-06)
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
CORS_EXPOSE_HEADERS = ["etag", "server-timing", "x-request-id"]

# ---------------------------------------------------------------------------------------
# Adapters (playbook 16). One interface each, a mock chosen by setting. A mock outside the
# named test environment refuses to boot (production-safety block).
# ---------------------------------------------------------------------------------------
LLM_PROVIDER = env_str("LLM_PROVIDER", "mock")  # mock | anthropic | bedrock
ANTHROPIC_API_KEY = env_str("ANTHROPIC_API_KEY", "")
EMBEDDER_PROVIDER = env_str("EMBEDDER_PROVIDER", "mock")  # mock | none | <chosen per D-09>
EMBEDDER_API_KEY = env_str("EMBEDDER_API_KEY", "")
EMBEDDING_DIMENSIONS = env_int("EMBEDDING_DIMENSIONS", 1024)  # DECISIONS D-09
AGENT_RUNNER = env_str("AGENT_RUNNER", "mock")  # mock | managed_agents
MAIL_PROVIDER = env_str("MAIL_PROVIDER", "mock")  # mock | smtp
MAIL_FROM = env_str("MAIL_FROM", "no-reply@localhost")
MAIL_SMTP_HOST = env_str("MAIL_SMTP_HOST", "")
MAIL_SMTP_PORT = env_int("MAIL_SMTP_PORT", 587)
MAIL_SMTP_USER = env_str("MAIL_SMTP_USER", "")
MAIL_SMTP_PASSWORD = env_str("MAIL_SMTP_PASSWORD", "")
# E4: the reranker over the fused top window (SRC-01, D-09). `none` is the contracted
# state until a model is chosen, and leaves the fused order as the answer.
RERANKER_PROVIDER = env_str("RERANKER_PROVIDER", "mock")  # mock | none | <chosen per D-09>
RERANKER_TOP_K = env_int("RERANKER_TOP_K", 50)
MOCK_ADAPTER_SETTINGS = ("LLM_PROVIDER", "EMBEDDER_PROVIDER", "RERANKER_PROVIDER", "AGENT_RUNNER", "MAIL_PROVIDER")

# ===== E3: the Anthropic provider behind the LLM adapter (chunks 5 and 7, D-07) =========
# The key is read from the environment only (ANTHROPIC_API_KEY above); everything the
# provider needs besides the key is a threshold with an env override. LLM_MAX_TOKENS is a
# ceiling: a caller asking for more gets this.
LLM_MODEL = env_str("LLM_MODEL", "claude-opus-5")
LLM_MAX_TOKENS = env_int("LLM_MAX_TOKENS", 4096)
# Per socket operation (the connect, then each read of the stream), not per call; also the
# longest a `retry-after` may hold a request.
LLM_TIMEOUT_S = float(env_str("LLM_TIMEOUT_S", "60.0"))
LLM_MAX_RETRIES = env_int("LLM_MAX_RETRIES", 2)
LLM_RETRY_BACKOFF_S = float(env_str("LLM_RETRY_BACKOFF_S", "0.5"))
# The whole call, retries and their waits included. No read starts after it, so a call
# ends within this plus one LLM_TIMEOUT_S (security review of E3, 2026-09-19).
LLM_DEADLINE_S = float(env_str("LLM_DEADLINE_S", "180.0"))
# The most a streamed answer may send, events and all, before it is refused. Several
# times what LLM_MAX_TOKENS can stream; raise the two together.
LLM_MAX_RESPONSE_BYTES = env_int("LLM_MAX_RESPONSE_BYTES", 4 * 1024 * 1024)
# An error body is read only this far, for its `error.type`.
LLM_MAX_ERROR_BODY_BYTES = env_int("LLM_MAX_ERROR_BODY_BYTES", 64 * 1024)

# ---------------------------------------------------------------------------------------
# ===== AUD-02 the AI output log (apps/governance/ai_log.py) =============================
# Two caps at one trust boundary: what a model wrote, and what an agent reported about it.
# Model output is text off a network and an agent's report is a caller's body, so neither
# is bounded by the provider's own token limit. Over the citation cap is a 422 naming the
# field; a longer output is stored up to the character cap, because the log keeps the
# record of what was said and not the whole transcript.
# ---------------------------------------------------------------------------------------
AI_GENERATION_OUTPUT_MAX_CHARS = env_int("AI_GENERATION_OUTPUT_MAX_CHARS", 20000)
AI_GENERATION_CITATIONS_MAX = env_int("AI_GENERATION_CITATIONS_MAX", 20)

# ---------------------------------------------------------------------------------------
# File storage (playbook 4.6). local for dev and tests, s3 when deployed. Nothing public.
# ---------------------------------------------------------------------------------------
STORAGE_BACKEND = env_str("STORAGE_BACKEND", "local")  # local | s3
MEDIA_ROOT = Path(env_str("STORAGE_LOCAL_ROOT", str(BASE_DIR / "var" / "media")))
STORAGE_S3_ENDPOINT_URL = env_str("STORAGE_S3_ENDPOINT_URL", "")
STORAGE_S3_BUCKET = env_str("STORAGE_S3_BUCKET", "")
STORAGE_S3_REGION = env_str("STORAGE_S3_REGION", "eu-west-1")
STORAGE_S3_ACCESS_KEY_ID = env_str("STORAGE_S3_ACCESS_KEY_ID", "")
STORAGE_S3_SECRET_ACCESS_KEY = env_str("STORAGE_S3_SECRET_ACCESS_KEY", "")

# ---------------------------------------------------------------------------------------
# WebAuthn (playbook 4.2, DECISIONS D-02). The RP ID is the exact app host.
# ---------------------------------------------------------------------------------------
WEBAUTHN_RP_ID = env_str("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = PRODUCT_NAME
WEBAUTHN_ORIGINS = env_list("WEBAUTHN_ORIGINS", "http://localhost:3000")
# The public URL of the web app, used in the emailed invitation link (ID-01). Defaults to
# the first CORS origin, which is the web app on every environment we run.
APP_BASE_URL = env_str("APP_BASE_URL", CORS_ALLOWED_ORIGINS[0] if CORS_ALLOWED_ORIGINS else "http://localhost:3000")

# ---------------------------------------------------------------------------------------
# ===== NFR-02 performance budgets (playbook 10) ==========================================
# ---------------------------------------------------------------------------------------
API_BUDGET_MS = env_int("API_BUDGET_MS", 250)
SEARCH_BUDGET_MS = env_int("SEARCH_BUDGET_MS", 800)
SEARCH_RERANKED_BUDGET_MS = env_int("SEARCH_RERANKED_BUDGET_MS", 1500)
API_PAGE_SIZE_DEFAULT = env_int("API_PAGE_SIZE_DEFAULT", 20)
API_PAGE_SIZE_MAX = env_int("API_PAGE_SIZE_MAX", 100)
# The largest offset a list accepts. PostgreSQL counts an OFFSET row by row and raises on a
# value beyond a signed 64-bit integer, so an unbounded offset turns every paginated route
# into a 500 (hardening H1). Above this the answer is a 422 naming the field, not a crash;
# nothing in the product pages that deep, and a reader that wants the far end filters.
API_PAGE_OFFSET_MAX = env_int("API_PAGE_OFFSET_MAX", 100000)
# Bounded like the diff cap below, and for the same reason: a typo here is not a slower
# product but a broken one. Below API_PAGE_SIZE_MAX no reader can reach the second page of
# a full list, and at 0 or below every list answers 422 to its own default offset. The
# production-safety block runs too late for this, so it refuses here.
if API_PAGE_OFFSET_MAX < API_PAGE_SIZE_MAX:
    raise ImproperlyConfigured(
        f"Refusing to boot: API_PAGE_OFFSET_MAX is {API_PAGE_OFFSET_MAX}, "
        f"below API_PAGE_SIZE_MAX ({API_PAGE_SIZE_MAX})."
    )

# ---------------------------------------------------------------------------------------
# ===== NFR-02 the performance harness (backend/perf/, scripts/perf_report.py) ============
# Ask's budget is the time to its first streamed chunk, not to the whole answer (playbook
# 10): the harness adds the wait for that chunk to the stream's Server-Timing. The other two
# are the harness's own. Twenty timed requests per route make the 95th percentile the
# second-slowest of them rather than a single outlier. A route fails the report when its
# median is more than PERF_REGRESSION_PCT per cent above its recorded baseline: tighter and
# the noise of a busy laptop fails routes nobody changed, looser and a real slowdown hides.
# The harness refuses a deployed environment, so the last two are never set on one.
# ---------------------------------------------------------------------------------------
ASK_FIRST_TOKEN_BUDGET_MS = env_int("ASK_FIRST_TOKEN_BUDGET_MS", 2000)
PERF_SAMPLES = env_int("PERF_SAMPLES", 20)
PERF_REGRESSION_PCT = env_int("PERF_REGRESSION_PCT", 20)

# ---------------------------------------------------------------------------------------
# ===== SRC-01..03 search and ask input caps (apps/search/schemas.py) =====================
# What a caller may send to search, to the similarity read and to Ask. Each is a cap at a
# trust boundary: the text reaches a text-search query, the embedder and, for Ask, a model
# prompt, and the budgets above are measured on queries of this size. Over the cap is a
# 422 naming the field, never a silent truncation that searches for something else.
# ---------------------------------------------------------------------------------------
SEARCH_QUERY_MAX_CHARS = env_int("SEARCH_QUERY_MAX_CHARS", 500)
SEARCH_SIMILAR_MAX_CHARS = env_int("SEARCH_SIMILAR_MAX_CHARS", 8000)
ASK_QUESTION_MAX_CHARS = env_int("ASK_QUESTION_MAX_CHARS", 2000)
SEARCH_FEEDBACK_NOTE_MAX_CHARS = env_int("SEARCH_FEEDBACK_NOTE_MAX_CHARS", 2000)

# ---------------------------------------------------------------------------------------
# ===== SRC-01 search index embedding (apps/search/indexing.py, apps/search/tasks.py) =====
# How many chunks one embedding call carries, and how often the sweep that drains the rest
# runs. An outbox delivery embeds one batch and stops, because it runs inside the cursor's
# transaction and holds the lock on the cursor row: a full-corpus rebuild that embedded
# everything there would make every other consumer's rows wait behind N model calls. The
# sweep takes the remainder on beat's clock, holding nothing anyone waits on, and it is
# also what picks up a rebuild whose outbox row spent its attempts and a corpus that was
# never embedded because no model was contracted yet.
# Raising the batch costs memory and the provider's own per-request limit; lowering it
# costs round trips. Nothing waits on either: a chunk with no embedding yet is still found
# by the keyword leg.
# ---------------------------------------------------------------------------------------
SEARCH_EMBED_BATCH_SIZE = env_int("SEARCH_EMBED_BATCH_SIZE", 64)
SEARCH_EMBED_SWEEP_INTERVAL_S = env_int("SEARCH_EMBED_SWEEP_INTERVAL_S", 60)
CELERY_BEAT_SCHEDULE["search-embed-backlog"] = {
    "task": "apps.search.tasks.embed_search_backlog",
    "schedule": SEARCH_EMBED_SWEEP_INTERVAL_S,
}

# ---------------------------------------------------------------------------------------
# ===== SRC-01, SRC-02 the fused hybrid query (apps/search/hybrid.py) =====================
# How the keyword leg and the vector leg are weighed against each other, how far down each
# of them a row still counts as found, and how much text a hit shows. Each is a lever on
# retrieval quality, so each is a setting the evaluation gate can be re-run against
# (backend/scripts/search_eval.py) rather than a number in the query.
#
# The rerank window is not here: `RERANKER_TOP_K` above is already "how many fused hits the
# reranker is given", and a second name for the same number is a way for the two to drift.
# ---------------------------------------------------------------------------------------
# Reciprocal rank fusion adds 1/(k + rank) per leg. k is how much a lower rank still counts:
# 60 is the constant the method was published with, and it means the difference between
# ranks 1 and 2 is worth more than the whole tail.
SEARCH_RRF_K = env_int("SEARCH_RRF_K", 60)
# How deep each leg reaches. A row ranked below this by a leg was not found by that leg, so
# it neither scores nor says it matched that way. Raising it widens the answer and slows the
# fusion; lowering it makes a long tail unreachable.
SEARCH_RETRIEVAL_DEPTH = env_int("SEARCH_RETRIEVAL_DEPTH", 50)
# The least cosine similarity that counts as a concept match. The vector leg always has a
# nearest neighbour, however far away, so without a floor every query would report every
# embedded chunk as a concept hit and "matched by meaning" would mean nothing. Half is
# where the mock embedder separates the two things it measures: a text that shares a
# concept with the question scores well above it, and one that merely repeats a few of its
# characters — an identifier and a reference number are the common case — scores below.
# It is re-tuned against the model D-09 chooses, whose similarities are on its own scale.
SEARCH_CONCEPT_SCORE_FLOOR = float(env_str("SEARCH_CONCEPT_SCORE_FLOOR", "0.5"))
# The most of a hit's text a snippet shows, cut around what matched. Long enough to judge a
# hit, short enough that a page of twenty is a page and not the library.
SEARCH_SNIPPET_CHARS = env_int("SEARCH_SNIPPET_CHARS", 240)

# ---------------------------------------------------------------------------------------
# ===== SRC-01, SRC-03, NFR-02 what one caller may spend (apps/search/limits.py) ==========
# Per caller per minute, in a fixed window: a person's session or an agent's key, each
# with a window of its own. Search is the whole index read twice and reranked; Ask is that
# plus a model call the bank pays for, so Ask is the tighter of the two. Sixty searches a
# minute is one a second, which no reader reaches and a runaway script passes at once; ten
# questions a minute is more than anyone asks and far less than a loop costs.
# ---------------------------------------------------------------------------------------
SEARCH_RATE_PER_USER_PER_MINUTE = env_int("SEARCH_RATE_PER_USER_PER_MINUTE", 60)
ASK_RATE_PER_USER_PER_MINUTE = env_int("ASK_RATE_PER_USER_PER_MINUTE", 10)
# Bounded, like the page offset and the diff cap above and for the same reason: at zero or
# below every call is over the limit and search stops answering at all, and there is no
# value of these that means "no limit" — a limit that can be configured away is not one.
# The production-safety block runs too late for this, so it refuses here.
if min(SEARCH_RATE_PER_USER_PER_MINUTE, ASK_RATE_PER_USER_PER_MINUTE) < 1:
    raise ImproperlyConfigured(
        f"Refusing to boot: SEARCH_RATE_PER_USER_PER_MINUTE is {SEARCH_RATE_PER_USER_PER_MINUTE} "
        f"and ASK_RATE_PER_USER_PER_MINUTE is {ASK_RATE_PER_USER_PER_MINUTE}; both must be at least 1."
    )

# ---------------------------------------------------------------------------------------
# ===== x-hardening-inputs-ask: open Ask streams, problem reports, visits (H38, H39, H47) =
# ASK_STREAMS_PER_USER is how many Ask answers one caller may have streaming at once
# (apps/search/limits.py). The per-minute rate above bounds how often a caller asks, not how
# long each answer holds a server thread (up to LLM_DEADLINE_S), so a few callers could
# otherwise hold every thread for every bank (H47). A slot is taken before the first byte
# and given back when the stream closes; a slot a lost worker never gave back expires
# ASK_STREAM_SLOT_TTL_S after the caller's last take, which is past the longest a model
# call can run.
# PROBLEM_REPORTS_PER_USER_PER_HOUR is how many problem reports one person may file, and
# separately close, in an hour (ACC-09, H39): each is a row and an audit row kept for ten
# years, and a script behind a session could file thousands.
# VISIT_MIN_INTERVAL_SECONDS: a `POST /me/visit` this soon after the person's last one
# writes nothing, since each writes an audit and an outbox row kept for ten years (H38).
# None of the three may be below 1: there is no value of them that means "no limit".
# ---------------------------------------------------------------------------------------
ASK_STREAMS_PER_USER = env_int("ASK_STREAMS_PER_USER", 2)
ASK_STREAM_SLOT_TTL_S = int(LLM_DEADLINE_S + LLM_TIMEOUT_S) + 60
PROBLEM_REPORTS_PER_USER_PER_HOUR = env_int("PROBLEM_REPORTS_PER_USER_PER_HOUR", 30)
VISIT_MIN_INTERVAL_SECONDS = env_int("VISIT_MIN_INTERVAL_SECONDS", 60)
for _name, _value in (
    ("ASK_STREAMS_PER_USER", ASK_STREAMS_PER_USER),
    ("PROBLEM_REPORTS_PER_USER_PER_HOUR", PROBLEM_REPORTS_PER_USER_PER_HOUR),
    ("VISIT_MIN_INTERVAL_SECONDS", VISIT_MIN_INTERVAL_SECONDS),
):
    if _value < 1:
        raise ImproperlyConfigured(f"Refusing to boot: {_name} is {_value}; it must be at least 1.")

# ---------------------------------------------------------------------------------------
# ===== SRC-03 Ask: what reaches the model and how much it may write (apps/search/ask.py) =
# How many passages of the hybrid ranking the model is given, and the most it may write
# back. The passages are the whole of what an answer may rest on, so a deeper retrieval is
# a wider answer and a longer prompt; each is also a numbered citation on the answer and
# on its AI log row, so the depth may not exceed the log's citation cap. The token cap is
# the answer's own ceiling beneath LLM_MAX_TOKENS: an answer is a few cited sentences, and
# a model that runs on is spending the bank's money on text nobody asked for.
# ---------------------------------------------------------------------------------------
ASK_RETRIEVAL_DEPTH = env_int("ASK_RETRIEVAL_DEPTH", 6)
ASK_MAX_TOKENS = env_int("ASK_MAX_TOKENS", 1024)
# At zero every question would be "no answer" without anyone having decided so, and above
# the citation cap an answer could cite a passage its log row cannot record.
if not 1 <= ASK_RETRIEVAL_DEPTH <= AI_GENERATION_CITATIONS_MAX or ASK_MAX_TOKENS < 1:
    raise ImproperlyConfigured(
        f"Refusing to boot: ASK_RETRIEVAL_DEPTH is {ASK_RETRIEVAL_DEPTH} (1 to "
        f"AI_GENERATION_CITATIONS_MAX, {AI_GENERATION_CITATIONS_MAX}) and ASK_MAX_TOKENS is "
        f"{ASK_MAX_TOKENS} (at least 1)."
    )

# ---------------------------------------------------------------------------------------
# ===== INV-04 "show what changed" (apps/library/logic.py sentence_diff) ==================
# Aligning two versions costs up to the cube of their sentence count when sentences repeat,
# and the texts come from fetched sources. Above this many sentences on either side the
# diff is the whole old text deleted and the whole new text inserted. The worst case measured
# 12 ms at 50 (29 ms under coverage on a loaded machine), 60 ms at 100 and 211 ms at 200,
# against API_BUDGET_MS for the whole request. A summary or a provision is a few sentences.
# ---------------------------------------------------------------------------------------
LIBRARY_DIFF_MAX_SENTENCES = env_int("LIBRARY_DIFF_MAX_SENTENCES", 50)
# Bounded, because this one is a cost ceiling on untrusted text and not a taste: at 0 or
# below no version is ever compared sentence by sentence and every diff is the whole text;
# above 200 the cubic cost runs away (211 ms measured at 200, about 7 s at 500). The
# production-safety block below runs too late for this, so it refuses here
# (apps/shared/tests_production_guard.py boots all four cases).
if not 1 <= LIBRARY_DIFF_MAX_SENTENCES <= 200:
    raise ImproperlyConfigured(
        f"Refusing to boot: LIBRARY_DIFF_MAX_SENTENCES is {LIBRARY_DIFF_MAX_SENTENCES}, "
        "which is outside 1 to 200."
    )
# The same, one level up: splitting a text into sentences is linear but unbounded in the
# length of the text, and a text is what a source published, through a proposal. 200 KB of
# short sentences measured 57 ms on the build machine and about half a second on the loaded
# laptop where the review found it. Above this many characters on either side the diff is
# the whole old text deleted and the whole new one inserted, with neither text split. A text
# that stays under the sentence cap above is a few thousand characters, so this cap only
# fires on text that would have been shown whole anyway.
LIBRARY_TEXT_MAX_CHARS = env_int("LIBRARY_TEXT_MAX_CHARS", 20000)

# ---------------------------------------------------------------------------------------
# ===== INV-03 library reads ==============================================================
# The most scope terms (`?term=dimension:key`) one list read accepts; they are resolved
# in one query, so the bound keeps that query and the URL short.
# ---------------------------------------------------------------------------------------
LIBRARY_TERM_FILTER_MAX = env_int("LIBRARY_TERM_FILTER_MAX", 20)

# ---------------------------------------------------------------------------------------
# ===== PRO-01 what a proposal may carry ==================================================
# A proposal arrives from an agent or a person over the network, so its two unbounded
# parts are bounded here. A field source is a link or a provision's stable key, and the
# longest source the library itself stores is `source_url`, a URLField of 2000 characters,
# so a field source is held to the same length. The scope terms are resolved in one query
# and stored twice (the payload and its audit row), so their number is bounded like the
# library's own term filter above.
# ---------------------------------------------------------------------------------------
PROPOSAL_SOURCE_MAX_CHARS = env_int("PROPOSAL_SOURCE_MAX_CHARS", 2000)
PROPOSAL_SCOPE_MAX_TERMS = env_int("PROPOSAL_SCOPE_MAX_TERMS", 20)

# ---------------------------------------------------------------------------------------
# ===== PRO-03 how far back "what changed in the library" looks ===========================
# A reader who has never marked the library as seen has no bookmark to read from, so the
# list falls back to this many days. Long enough that a first visit is not empty and a
# fortnight away still shows the fortnight; short enough that the first read is a page and
# not the whole history, which is what the inventory itself is for.
# ---------------------------------------------------------------------------------------
LIBRARY_UPDATES_DEFAULT_DAYS = env_int("LIBRARY_UPDATES_DEFAULT_DAYS", 30)

# ---------------------------------------------------------------------------------------
# ===== INV-06 what a person types on a library record ====================================
# The longest "this looks wrong" description and re-verification note the API accepts. A
# report says what looks wrong and which words were on screen; it is not a document, and
# an unbounded free-text field at a trust boundary is a way to fill a table.
# ---------------------------------------------------------------------------------------
LIBRARY_REPORT_TEXT_MAX_CHARS = env_int("LIBRARY_REPORT_TEXT_MAX_CHARS", 4000)

# ---------------------------------------------------------------------------------------
# ===== AUD-01, CAS-01 the outbox cursor (apps/shared/outbox.py, c5-outbox-cursor) ========
# One worker delivers `outbox_event` in `(created, id)` order. The batch size bounds one
# pass, which holds the cursor's row lock for its duration; the poll interval is how often
# beat runs it, and it is also the longest a change waits for its case at an idle moment.
# A handler that raises is tried again after the backoff, doubled per attempt (60 s, 120 s,
# 240 s, 480 s at the defaults); after the last attempt the row is left failed and the
# cursor moves on, so one broken consumer cannot stop every other row forever.
# ---------------------------------------------------------------------------------------
OUTBOX_BATCH_SIZE = env_int("OUTBOX_BATCH_SIZE", 100)
OUTBOX_POLL_INTERVAL_S = env_int("OUTBOX_POLL_INTERVAL_S", 10)
OUTBOX_MAX_ATTEMPTS = env_int("OUTBOX_MAX_ATTEMPTS", 5)
OUTBOX_RETRY_BACKOFF_S = env_int("OUTBOX_RETRY_BACKOFF_S", 60)
# The beat entry that runs it. CELERY_BEAT_SCHEDULE is declared empty in the Celery block
# above, which is the one place the worker, beat and the test runner read; the interval
# has to be defined before an entry can name it, so the entry is added here beside it.
CELERY_BEAT_SCHEDULE["outbox-deliver"] = {
    "task": "apps.shared.tasks.deliver_outbox",
    "schedule": OUTBOX_POLL_INTERVAL_S,
}

# ---------------------------------------------------------------------------------------
# ===== CAS-01 one case per bank per change (apps/cases/creation.py, c5-cases-creation) ===
# A registered change opens a case in every active bank, on the cursor above and never in
# the request that registered it. This is how many bank ids come back per round trip while
# the fan-out reads the list, so a change reaching hundreds of banks costs a handful of
# fetches; each bank's case is then one insert of its own, because a session writes one
# zone and no insert can span two.
# ---------------------------------------------------------------------------------------
CASE_CREATION_BATCH = env_int("CASE_CREATION_BATCH", 100)

# ---------------------------------------------------------------------------------------
# ===== WAT-01 when a watched source has gone stale (apps/watch/sources.py) ===============
# The console's Source coverage says "we missed nothing" only as far as the coverage log
# lets it. A source is stale when the last SOURCE_STALE_AFTER_CHECKS sweeps of it all
# failed — one, by default, because a supervisor's page that will not answer is news the
# moment it happens — or when longer than its own cadence plus SOURCE_STALE_GRACE_HOURS
# has passed since the last sweep that succeeded. The grace exists because a run is
# scheduled rather than instantaneous: a daily source checked a few hours late is late,
# not unwatched, and a grace of a day keeps the page free of rows nobody can act on.
# ---------------------------------------------------------------------------------------
SOURCE_STALE_AFTER_CHECKS = env_int("SOURCE_STALE_AFTER_CHECKS", 1)
SOURCE_STALE_GRACE_HOURS = env_int("SOURCE_STALE_GRACE_HOURS", 24)

# ---------------------------------------------------------------------------------------
# ===== WAT-07 standards publishers nobody reads automatically (apps/watch/sources.py) ====
# A source whose address is on one of these hosts, or a subdomain of one, is registered
# with its automated checks off, like every source of the `standards_body` kind, and a run
# may log no check of it. Comma-separated host names. The default names every standards
# publisher whose terms docs/plans/Verification_Log.md ("PRD 0.3 standards facts") read, so
# out of the box bleqq reads no publisher automatically; a host leaves the list only when a
# lawyer has cleared its terms (D-45, docs/TODO_FOR_alex.md "Legal, before any standard is
# seeded"). IAF is not on it: it publishes no standard's text.
# ---------------------------------------------------------------------------------------
STANDARDS_PUBLISHER_HOSTS = [host.lower() for host in env_list(
        "STANDARDS_PUBLISHER_HOSTS", "iso.org,iec.ch,sis.se,ds.dk,standard.no,sfs.fi,pcisecuritystandards.org"
    )]

# ---------------------------------------------------------------------------------------
# ===== AGT-01, WAT-01 what one agent run may file (HARDENING H41, agent-write-guards) ====
# The server holds every run to the write budgets its definition names
# (`budget_defaults` in backend/agents/watch-sweeper/v1/definition.yaml): new proposals,
# new changes on the watch feed and re-check lines of the coverage log. A write past its
# budget answers 422 `run_budget_exhausted` and stores nothing, so a runaway or injected
# run cannot flood the review queue under one open run. A budget below 1 would refuse
# every run's first write, so it refuses to boot instead.
# ---------------------------------------------------------------------------------------
WATCH_RUN_MAX_PROPOSALS = env_int("WATCH_RUN_MAX_PROPOSALS", 50)
WATCH_RUN_MAX_CHANGES = env_int("WATCH_RUN_MAX_CHANGES", 50)
WATCH_RUN_MAX_RECHECKS = env_int("WATCH_RUN_MAX_RECHECKS", 100)
if min(WATCH_RUN_MAX_PROPOSALS, WATCH_RUN_MAX_CHANGES, WATCH_RUN_MAX_RECHECKS) < 1:
    raise ImproperlyConfigured(
        "Refusing to boot: WATCH_RUN_MAX_PROPOSALS, WATCH_RUN_MAX_CHANGES and WATCH_RUN_MAX_RECHECKS are each at least 1."
    )

# ---------------------------------------------------------------------------------------
# ===== HOM-01 how long Today's "Coming up" list is (apps/home/logic.py, c6-home-backend) =
# Today shows the same short list on a 375 px phone and on a desktop, so its length is one
# number rather than a breakpoint: the screen never decides how much of the roadmap it is
# allowed to show. Five is what the designed screen holds above the fold on a phone, and
# the count beside the list says how many more the roadmap has, so nothing is hidden by it.
# ---------------------------------------------------------------------------------------
HOME_COMING_UP_ITEMS = env_int("HOME_COMING_UP_ITEMS", 5)

# ---------------------------------------------------------------------------------------
# ===== HOM-02 the weekly briefing and its mail (apps/home/tasks.py, c6-briefing-backend) =
# The mail goes out on the bank's own Monday morning and covers the week that has just
# ended, which is the only moment a week can be summed up; the designed screen says the
# same ("the weekly email on Monday 07:00"). Both are settings rather than literals because
# a bank may want its briefing on a Friday afternoon instead, and neither number is a rule.
# The weekday is Python's: Monday is 0. The hour is the bank's own local hour, which is why
# the beat entry below runs every hour and the task picks the banks whose clock has just
# struck it — one schedule serving banks in several time zones.
# The cap is what one mail and one page can carry without becoming a list nobody reads; the
# rest of the week stays on the feed, which the briefing links to.
# ---------------------------------------------------------------------------------------
BRIEFING_SEND_WEEKDAY = env_int("BRIEFING_SEND_WEEKDAY", 0)
BRIEFING_SEND_HOUR = env_int("BRIEFING_SEND_HOUR", 7)
BRIEFING_MAX_ITEMS = env_int("BRIEFING_MAX_ITEMS", 10)
CELERY_BEAT_SCHEDULE["briefing-weekly"] = {
    "task": "apps.home.tasks.send_weekly_briefings",
    "schedule": crontab(minute="0"),
}

# ---------------------------------------------------------------------------------------
# ===== HOM-04 the calendar subscription's limits (D-52, ADR 0045) ========================
# The token in a calendar address is a credential nobody can be asked to confirm: a
# calendar client sends no header, follows no sign-in and polls unattended for years. Two
# numbers bound what that is worth to whoever finds one. A person keeps a handful of
# subscriptions, not an inventory, so a compromised session cannot mint addresses without
# anyone noticing; and a subscription nobody has fetched for a month is a calendar that was
# removed or a device that was replaced, so it expires rather than working forever. Both
# are settings because a bank's own guidance may be stricter and neither number is a rule.
# `apps/home/feed.py` reads them when a subscription is made, listed and fetched.
# ---------------------------------------------------------------------------------------
CALENDAR_FEEDS_PER_USER = env_int("CALENDAR_FEEDS_PER_USER", 5)
CALENDAR_FEED_IDLE_DAYS = env_int("CALENDAR_FEED_IDLE_DAYS", 30)
# How many stopped subscriptions a person's list shows beside the ones that work, most
# recently stopped first. Enough to show a whole set of addresses just replaced; the list
# stays short however many a person has replaced over the years, which is what lets it go
# unpaged (the live ones are capped above).
CALENDAR_FEED_REVOKED_SHOWN = env_int("CALENDAR_FEED_REVOKED_SHOWN", 5)
# How often one address may be fetched. A calendar client polls every few hours, so this
# is generous for every real client and still bounds what someone who found an address
# can pull from it. It is per token, so a flood on one address leaves the others answering.
CALENDAR_FEED_RATE_PER_MINUTE = env_int("CALENDAR_FEED_RATE_PER_MINUTE", 20)
# How often a fetch moves `last_used_at` and writes its `feed_used` security-log row, as
# an API key's stamp is throttled (ID-10). Without it a polling client would turn a read
# into a write every time and fill the security log with one bank's polling.
CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS = env_int("CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS", 300)

# ---------------------------------------------------------------------------------------
# ===== HOM-05 My work's windows (apps/home/my_work.py, c8-mywork-service, D-23, D-25) ===
# A row is "due soon" when its next date is today or within MY_WORK_DUE_SOON_DAYS; the
# tenant's reminder lead replaces it once COL-02 lands. A new version of an obligation stays
# under "Changes on your items" for MY_WORK_AWARE_DAYS after it was applied: a fixed window
# needs no write on every page load. Each is at least 1, or the app refuses to boot.
# ---------------------------------------------------------------------------------------
MY_WORK_DUE_SOON_DAYS = env_int("MY_WORK_DUE_SOON_DAYS", 30)
MY_WORK_AWARE_DAYS = env_int("MY_WORK_AWARE_DAYS", 14)
if min(MY_WORK_DUE_SOON_DAYS, MY_WORK_AWARE_DAYS) < 1:
    raise ImproperlyConfigured("Refusing to boot: MY_WORK_DUE_SOON_DAYS and MY_WORK_AWARE_DAYS are each at least 1.")

# ---------------------------------------------------------------------------------------
# ===== Health check (playbook 2.2, 5) ====================================================
# The worker ping is bounded to one reply so a large fleet never makes /health/ slow.
# ---------------------------------------------------------------------------------------
HEALTH_WORKER_PING_TIMEOUT_S = float(env_str("HEALTH_WORKER_PING_TIMEOUT_S", "1.0"))
HEALTH_WORKER_PING_LIMIT = 1

# ---------------------------------------------------------------------------------------
# ===== ID-02, ID-03 enrolment code and invitation windows (playbook 4.2) ===============
# Chunk 1 reads these; they exist from Phase 0 so no number is ever a literal in logic.
# ---------------------------------------------------------------------------------------
INVITATION_TTL_HOURS = env_int("INVITATION_TTL_HOURS", 72)
ENROLMENT_CODE_DIGITS = env_int("ENROLMENT_CODE_DIGITS", 6)
ENROLMENT_CODE_TTL_MINUTES = env_int("ENROLMENT_CODE_TTL_MINUTES", 10)
ENROLMENT_CODE_MAX_ATTEMPTS = env_int("ENROLMENT_CODE_MAX_ATTEMPTS", 5)
ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR = env_int("ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR", 5)
ENROLMENT_CODE_RATE_PER_IP_PER_HOUR = env_int("ENROLMENT_CODE_RATE_PER_IP_PER_HOUR", 20)
# Every other auth ceremony endpoint (verify code, passkey sign-in, refresh) per IP.
AUTH_RATE_PER_IP_PER_MINUTE = env_int("AUTH_RATE_PER_IP_PER_MINUTE", 30)
# How many proxies of ours append to X-Forwarded-For before a request reaches the app.
# 0 (the default) means the socket address is the client: the header is then ignored,
# because a caller can write anything into it and would otherwise pick its own address
# for the per-IP limits and the security log. Set to 1 behind one edge proxy (Railway).
TRUSTED_PROXY_HOPS = env_int("TRUSTED_PROXY_HOPS", 0)
# A WebAuthn challenge lives this long (registration, sign-in and step-up ceremonies).
CHALLENGE_TTL_SECONDS = env_int("CHALLENGE_TTL_SECONDS", 120)
# The one deterministic code E2E journeys type (playbook 8.3). Read only when E2E_MODE is
# on, which the production-safety block refuses when deployed (rule 4) and the code logic
# refuses again on its own leg.
E2E_FIXED_CODE = "123456"

# ---------------------------------------------------------------------------------------
# ===== ID-06, ID-08 sessions and step-up (DECISIONS D-06) ================================
# ---------------------------------------------------------------------------------------
SESSION_IDLE_MINUTES_DEFAULT = env_int("SESSION_IDLE_MINUTES_DEFAULT", 30)
SESSION_ABSOLUTE_HOURS_DEFAULT = env_int("SESSION_ABSOLUTE_HOURS_DEFAULT", 12)
SESSION_IDLE_MINUTES_MAX = env_int("SESSION_IDLE_MINUTES_MAX", 8 * 60)
SESSION_ABSOLUTE_HOURS_MAX = env_int("SESSION_ABSOLUTE_HOURS_MAX", 24)
# ===== c8-org-models: ID-07 credential policy (ADR 0048) =====
# How many days ahead a tightened credential policy takes effect by default, so members can
# enrol a device-bound passkey before theirs stop working (tenants.SecurityPolicy).
CREDENTIAL_POLICY_NOTICE_DAYS = env_int("CREDENTIAL_POLICY_NOTICE_DAYS", 14)
ACCESS_TOKEN_TTL_MINUTES = env_int("ACCESS_TOKEN_TTL_MINUTES", 10)
REFRESH_REPLAY_GRACE_SECONDS = env_int("REFRESH_REPLAY_GRACE_SECONDS", 30)
STEP_UP_FRESHNESS_MINUTES = env_int("STEP_UP_FRESHNESS_MINUTES", 5)
# The rotating refresh token's cookie (ADR 0006): HttpOnly, Secure outside DEBUG,
# SameSite=Strict, scoped to the auth path so no other route ever receives it.
REFRESH_COOKIE_NAME = "cw_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_SECURE = not DEBUG
# An API key's last_used_at (and its key_used security-log row) is written at most this
# often, so a busy agent does not turn every call into a write (ID-10).
API_KEY_LAST_USED_THROTTLE_SECONDS = env_int("API_KEY_LAST_USED_THROTTLE_SECONDS", 60)

# ---------------------------------------------------------------------------------------
# ===== Rate limiting (playbook 11.2). Off in tests (test_settings override 6). ===========
# ---------------------------------------------------------------------------------------
RATE_LIMITING_ENABLED = env_bool("RATE_LIMITING_ENABLED", True)

# ---------------------------------------------------------------------------------------
# Logging (playbook 4.7): structured JSON with the request ID on every line. Personal data
# is limited to a person's name and id; tenant content never appears. The compliance lint
# checks call sites; this block only shapes the output.
# ---------------------------------------------------------------------------------------
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.shared.middleware.RequestIdLogFilter"}},
    "formatters": {
        "json": {
            "()": "apps.shared.logging.JsonFormatter",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
# ===== SRC-03 Ask: no tenant text through django.template's DEBUG lines ================
# Ninja reads a response attribute it cannot find through Django's template `Variable`,
# which logs the miss at DEBUG with the object's repr, and an Ask event's repr holds the
# question the reader typed. So this one logger stays at INFO whatever LOG_LEVEL says
# (apps/search/tests_ask.py, AskPrivacyTests).
LOGGING["loggers"]["django.template"] = {"level": "INFO"}  # type: ignore[index]

# ---------------------------------------------------------------------------------------
# Sentry (playbook 11.2), only when SENTRY_DSN is set, on the EU region. No PII, no
# request bodies, no local variables, and both scrubbers: transactions bypass before_send
# and a 10% trace sample silently exempted one in ten requests in the last repo.
# ---------------------------------------------------------------------------------------
SENTRY_DSN = env_str("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = float(env_str("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import ignore_logger

    from apps.shared.sentry_scrub import before_send, before_send_transaction  # noqa: E402

    # gunicorn writes each access line at INFO outside any request scope, so as a
    # breadcrumb it would ride on the next event, whoever's request that is (security
    # review 2026-09-19). The line is in the container log already; Sentry never needs it.
    ignore_logger("gunicorn.access")
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=HOST_ENVIRONMENT_NAME or ENVIRONMENT,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        before_send=before_send,
        before_send_transaction=before_send_transaction,
    )

# ---------------------------------------------------------------------------------------
# ===== Production-safety block (playbook 11.1) ===========================================
# The rationale lives here; apps/shared/tests_production_guard.py boots Django in
# subprocesses under `prod`, `Production`, `demo`, `dev`, `local`, `test` and `ci` to prove
# every branch. A guard that cannot fail is decoration.
#
#  1. Deployed is the default. Only `local`, `test` and `ci` without a host environment
#     name are non-deployed; anything else, and any RAILWAY_ENVIRONMENT_NAME, is deployed.
#  2. DEBUG on a deployed environment leaks settings, SQL and stack traces to the browser.
#  3. The default SECRET_KEY signs nothing safely. It is tolerated only on the three
#     non-deployed names (local, test, ci: laptops and CI runners set no key), refused on
#     every deployed environment whatever DEBUG says.
#  4. E2E_MODE makes the enrolment code deterministic. That is fine on a laptop or a CI
#     runner and catastrophic anywhere reachable from the internet (PRD ID-02, ID-03).
#  5. A mock LLM, embedder, agent runner or mailer on a deployed environment other than
#     the one named `test` means silent no-ops: emails that never send, agent runs that
#     never happen, embeddings that are zeros. `test` may run mocks and shows a banner.
#  6. The local file backend is a container's ephemeral disk. Evidence written there is
#     lost on the next deploy (playbook 4.6), so deployed environments must use s3.
#  7. The database role: checked at boot against the live connection by
#     apps.shared.db_role_guard (superuser, table owner, BYPASSRLS all skip policies:
#     Verification_Log, PostgreSQL row security). It cannot be checked here because
#     settings must not open connections; SharedConfig.ready() does it.
#  8. The WebAuthn RP ID is the exact app host (ADR 0002). A deployed environment that
#     still says `localhost` would enrol passkeys nobody can use from the real host, so
#     it refuses to boot until WEBAUTHN_RP_ID and WEBAUTHN_ORIGINS name the host.
#  9. RATE_LIMITING_ENABLED=false switches every bucket off at once: the sign-in
#     ceremonies' (ID-02) and search's and Ask's, which cap what one caller spends of the
#     model budget (NFR-02). Each bucket's own size already refuses to boot below 1, so the
#     switch is the one way left to turn them off, and it stays for laptops and tests only
#     (security-review-c7, M2).
# ---------------------------------------------------------------------------------------
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
if STORAGE_BACKEND not in {"local", "s3"}:
    _refuse(f"STORAGE_BACKEND={STORAGE_BACKEND!r} is not one of local, s3.")

logging.getLogger(__name__).debug(
    "settings loaded", extra={"environment": ENVIRONMENT, "deployed": IS_DEPLOYED_ENVIRONMENT}
)
