# Compliance Watch API image (playbook 12: container-only, twelve-factor, non-root, a
# HEALTHCHECK on /health/). The same image runs the worker and beat with a start command
# override (docs/runbooks/RAILWAY_DEPLOY.md).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.0.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# Poetry resolves from the committed lockfile only; a lockfile drift fails the build here
# rather than at runtime.
RUN pip install "poetry==${POETRY_VERSION}"
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY . .

# Non-root from here on. The media directory exists only for the local backend, which a
# deployed environment refuses at boot (settings rule 6); it is harmless empty.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/var/media \
    && chown -R app:app /app \
    && chmod +x /app/docker-entrypoint.sh
USER app

EXPOSE 8000

# python:slim has no curl; a Python one-liner keeps the image small. 503 exits non-zero.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
