"""Celery application (playbook 12: worker and beat are separate services from the same
image). Business-time schedules live in `beat_schedule` and run per tenant timezone
inside `@tenant_task` tasks; a host cron is UTC and only triggers.

`apps.shared.tests_celery_registration` walks `app.conf.beat_schedule` and every task
module, so a beat entry that points at a missing task fails the build, not the night."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("compliance_watch")
# Every CELERY_* setting lives in config/settings.py so the worker, beat and the test
# runner read one source (test_settings makes tasks eager, override 4).
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(related_name="tasks")
