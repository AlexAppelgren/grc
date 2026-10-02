"""The library baseline's runner on the beat (D-118, ADR 0065).

Not a `@tenant_task`: it activates no tenant and files only shared proposals, as the
command does from the API's shell. `LIBRARY_BASELINE_FILING_MINUTES` sets how often it runs
and switches it off at 0 (config/settings.py)."""

from __future__ import annotations

from celery import shared_task

from apps.proposals import baseline


@shared_task
def file_library_baseline() -> None:
    """Register the sources the baseline names, then file every entry now due: the
    instruments the library does not hold, and the duties of every instrument it does."""
    baseline.register_sources()
    baseline.file()
