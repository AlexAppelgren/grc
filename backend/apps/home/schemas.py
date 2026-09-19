"""Request and response schemas of the home app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1)."""

from apps.shared.schemas import CamelSchema

__all__ = ["CamelSchema"]
