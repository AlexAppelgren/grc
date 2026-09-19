"""URL configuration. The versioned API at /api/v1 (Django Ninja) and the health check at
/health/ outside it, because the health check must answer without the API's auth or
CORS scoping (playbook 2.2). There is no admin URL, on purpose (playbook 4.3)."""

from django.urls import path

from apps.shared.health_check import health_view
from config.api import api

urlpatterns = [
    path("api/v1/", api.urls),
    path("health/", health_view, name="health"),
]
