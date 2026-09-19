"""Routes of the watch app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1). Mounted in config/api.py once the
first route lands."""

from ninja import Router

router = Router(tags=["Watch"])
