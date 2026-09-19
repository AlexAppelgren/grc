# Compliance Watch API image (playbook 12: container-only, twelve-factor, non-root, a
# HEALTHCHECK on /health/). The same image runs the worker and beat with a start command
# override (docs/runbooks/RAILWAY_DEPLOY.md).
#
# Two stages on Alpine, on purpose. The first CI container scan (2026-09-19) failed the
# single-stage Debian image: Poetry and its dependencies (dulwich) sat in the runtime
# layer with advisories, and the Debian base carried 91 MEDIUM and HIGH findings with no
# fix published upstream, which no line in this file could ever clear. Alpine's base
# scanned clean the same day. Now Poetry lives only in the builder, the runtime copies the
# finished virtualenv, and pip is removed from both because nothing installs at runtime.
# The gate is "no MEDIUM or above finding in the image, fixed or not" (ADR 0025).

FROM python:3.12-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.0.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# gcc and friends exist only in this stage, for any wheel that must compile on musl.
# Poetry resolves from the committed lockfile only; a lockfile drift fails the build here
# rather than at runtime. The virtualenv lands in /app/.venv and is copied as-is below,
# so the path must be the same in both stages.
RUN apk add --no-cache build-base libffi-dev \
    && pip install "poetry==${POETRY_VERSION}"
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root \
    && rm -rf /app/.venv/lib/python3.12/site-packages/pip \
              /app/.venv/lib/python3.12/site-packages/pip-*.dist-info \
              /app/.venv/bin/pip /app/.venv/bin/pip3 /app/.venv/bin/pip3.12


FROM python:3.12-alpine AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Alpine security updates for the base, then the system pip goes: the runtime installs
# nothing, and the bundled pip carried nine MEDIUM advisories on 2026-09-19.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip \
              /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
              /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . .

# Non-root from here on. The media directory exists only for the local backend, which a
# deployed environment refuses at boot (settings rule 6); it is harmless empty.
RUN adduser -D -u 10001 app \
    && mkdir -p /app/var/media \
    && chown -R app:app /app \
    && chmod +x /app/docker-entrypoint.sh
USER app

EXPOSE 8000

# The base has no curl; a Python one-liner keeps the image small. 503 exits non-zero.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
