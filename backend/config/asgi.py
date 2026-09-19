"""ASGI entry point. Not used by the deploy (gunicorn serves WSGI); kept so a streaming
Ask endpoint (playbook 10) can move to ASGI without a new file."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
