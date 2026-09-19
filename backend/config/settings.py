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
if STORAGE_BACKEND not in {"local", "s3"}:
    _refuse(f"STORAGE_BACKEND={STORAGE_BACKEND!r} is not one of local, s3.")

logging.getLogger(__name__).debug(
    "settings loaded", extra={"environment": ENVIRONMENT, "deployed": IS_DEPLOYED_ENVIRONMENT}
)
