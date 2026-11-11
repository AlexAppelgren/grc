"""Tenancy and the two zones (playbook 14).

- `clear_tenant()` and `platform_zone()` leave the tenant zone, for the transaction or a
  block, since a mixed table accepts only the session's own zone (H15). The tenancy guard
  pins who may call them.
- `activate(tenant_id)` issues `SET LOCAL app.tenant_id` (via `set_config(..., true)`) in the
  open transaction; policies read `current_setting('app.tenant_id', true)`, so unset matches
  nothing. It refuses to run outside a transaction, where `SET LOCAL` is a silent no-op.
- `@tenant_task` takes the tenant id as a Celery task's first argument and activates it in
  the task's own transaction.
- `TenantModel`: abstract, `tenant` FK, under forced RLS.
- `LibraryModel`: abstract, no tenant; written only inside `library_write()`, which the
  library-fence guard restricts to the proposal applier, the watch pipeline and the seeds
  (PRO-01).
- `library_door()` is the database's half of that fence (H16, ADR 0058): a transaction-local
  setting naming the door, which a trigger on every library-zone table checks.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal, TypeVar

from django.db import DEFAULT_DB_ALIAS, connections, models, transaction

from apps.shared.migration_helpers import LIBRARY_DOOR_SETTING

TENANT_SETTING = "app.tenant_id"
# The identity-lookup flag: five tables are read before any tenant is known (an invitation, a
# membership at sign-in, a session by refresh cookie, an API key by prefix, a calendar feed by
# its token, D-52). Their policies add `OR current_setting('app.identity_lookup', true) =
# 'on'`, switched on by `identity_lookup()` for the shortest block. apps/shared/tests_rls.py
# lists the tables, and an AST guard restricts the callers to authentication and identity.
IDENTITY_LOOKUP_SETTING = "app.identity_lookup"
# The door a library-zone write comes through (H16, ADR 0058); the trigger on every
# library-zone table refuses an app-role write unless `LIBRARY_DOOR_SETTING` names a door that
# table accepts (see the migration helpers). The compliance lint's `library-door` rule keeps
# this name to the doors, the migration helpers, migrations and tests.
LibraryDoor = Literal["proposal", "reverification", "seed", "watch", "index", "eval"]

_active_tenant: ContextVar[uuid.UUID | None] = ContextVar("active_tenant", default=None)
_library_write_reason: ContextVar[str | None] = ContextVar("library_write_reason", default=None)


class NotInTransaction(RuntimeError):
    """activate() was called outside a transaction, where SET LOCAL would do nothing."""


class LibraryWriteRefused(RuntimeError):
    """A library row was written outside library_write() (PRO-01)."""


def activate(tenant_id: uuid.UUID, *, using: str = DEFAULT_DB_ALIAS) -> None:
    """Scope the current transaction to one tenant. Called after authentication resolves
    the membership (request) or at the top of a tenant task (worker). `using` exists for
    the RLS guard, which activates on the cw_app alias."""
    connection = connections[using]
    if not connection.in_atomic_block:
        raise NotInTransaction(
            "tenancy.activate() needs an open transaction: SET LOCAL is a no-op outside one. "
            "Requests run under ATOMIC_REQUESTS; tasks use @tenant_task."
        )
    _set_tenant_setting(str(tenant_id), using=using)
    _active_tenant.set(tenant_id)


def active_tenant_id() -> uuid.UUID | None:
    """The tenant this context activated, if any. Python-side mirror of the GUC."""
    return _active_tenant.get()


def database_tenant_id(*, using: str = DEFAULT_DB_ALIAS) -> uuid.UUID | None:
    """What the database itself thinks the tenant is: the value policies see."""
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT NULLIF(current_setting(%s, true), '')", [TENANT_SETTING])
        row = cursor.fetchone()
    value = row[0] if row else None
    return uuid.UUID(value) if value else None


def clear_tenant(*, using: str = DEFAULT_DB_ALIAS) -> None:
    """Leave the tenant zone for the rest of the transaction, as a request with no tenant
    runs. `platform_zone()` is the block form; the tenancy guard pins who may call either."""
    connection = connections[using]
    if not connection.in_atomic_block:
        raise NotInTransaction("tenancy.clear_tenant() needs an open transaction: SET LOCAL is a no-op outside one.")
    _set_tenant_setting("", using=using)
    _active_tenant.set(None)


@contextmanager
def platform_zone(*, using: str = DEFAULT_DB_ALIAS) -> Iterator[None]:
    """Write rows that belong to no tenant, inside the open transaction, then put the
    session's tenant back. A mixed table accepts only the session's zone (H15), so a bank's
    session writes a library or console subject's audit row here. A block that raises leaves
    the tenant as it found it.
    """
    previous = database_tenant_id(using=using)
    clear_tenant(using=using)
    try:
        yield
    finally:
        _set_tenant_setting(str(previous) if previous else "", using=using)
        _active_tenant.set(previous)


def _set_tenant_setting(value: str, *, using: str) -> None:
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [TENANT_SETTING, value])


class IdentityLookup:
    """What `identity_lookup()` hands its block. `then_activate` activates the credential's
    tenant (or none) in the same statement that switches the lookup off, one round trip for
    both, and only when the block ends without an error."""

    def __init__(self) -> None:
        self.zone: uuid.UUID | None = None
        self.entering = False

    def then_activate(self, tenant_id: uuid.UUID | None) -> None:
        self.zone, self.entering = tenant_id, True


@contextmanager
def identity_lookup(*, using: str = DEFAULT_DB_ALIAS) -> Iterator[IdentityLookup]:
    """Read identity rows of any tenant for the duration of the block, inside the open
    transaction, then switch the flag off again. Only the auth layer may use it."""
    connection = connections[using]
    if not connection.in_atomic_block:
        raise NotInTransaction("tenancy.identity_lookup() needs an open transaction: SET LOCAL is a no-op outside one.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [IDENTITY_LOOKUP_SETTING, "on"])
    lookup = IdentityLookup()
    entering = False
    try:
        yield lookup
        entering = lookup.entering
    finally:
        with connection.cursor() as cursor:
            if entering:
                cursor.execute(
                    "SELECT set_config(%s, %s, true), set_config(%s, %s, true)",
                    [IDENTITY_LOOKUP_SETTING, "", TENANT_SETTING, str(lookup.zone) if lookup.zone else ""],
                )
                _active_tenant.set(lookup.zone)
            else:
                cursor.execute("SELECT set_config(%s, %s, true)", [IDENTITY_LOOKUP_SETTING, ""])


F = TypeVar("F", bound=Callable[..., Any])


def tenant_task(fn: F) -> F:
    """Wrap a task body so it takes `tenant_id` first and runs activated in its own
    transaction. The Celery registration guard demands this on every tenant task."""

    @functools.wraps(fn)
    def wrapper(tenant_id: uuid.UUID | str, *args: Any, **kwargs: Any) -> Any:
        tid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
        previous = _active_tenant.get()
        with transaction.atomic():
            activate(tid)
            try:
                return fn(tid, *args, **kwargs)
            finally:
                _active_tenant.set(previous)

    wrapper.__cw_tenant_task__ = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


# --- Library fence ---
@contextmanager
def library_write(reason: str, *, door: LibraryDoor = "seed") -> Iterator[None]:
    """The only context in which a LibraryModel may be saved or deleted. `reason` names the
    proposal, the watch step or the seed.

    `door` is what the database is told (H16, ADR 0058): `proposal` or `reverification` for
    the proposal applier, `watch` for the watch door, the default `seed` for reference seeds
    and test builders. The library fence pins which module may name which door."""
    if not reason.strip():
        raise ValueError("library_write() needs a reason naming the proposal, step or seed")
    token = _library_write_reason.set(reason)
    try:
        with library_door(door):
            yield
    finally:
        _library_write_reason.reset(token)


@contextmanager
def library_door(door: LibraryDoor, *, using: str = DEFAULT_DB_ALIAS) -> Iterator[None]:
    """Tell the database which door the writes in this block come through (H16, ADR 0058).

    The setting is transaction-local, so the block runs in its own transaction or a
    savepoint. The door found is put back on the way out, so doors nest; a raising block
    rolls back, and the setting with it. `using` lets the guard prove the trigger on cw_app."""
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            cursor.execute("SELECT coalesce(current_setting(%s, true), '')", [LIBRARY_DOOR_SETTING])
            row = cursor.fetchone()
            cursor.execute("SELECT set_config(%s, %s, true)", [LIBRARY_DOOR_SETTING, door])
        yield
        with connections[using].cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, true)", [LIBRARY_DOOR_SETTING, row[0] if row else ""])


def _assert_library_write(model_name: str) -> None:
    if _library_write_reason.get() is None:
        raise LibraryWriteRefused(
            f"{model_name} is a library record. Writes happen only inside library_write() "
            "from proposals/apply.py, watch/write.py or a reference seed (PRO-01)."
        )


class LibraryQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> int:  # compliance: allow-kwargs Django QuerySet signature
        _assert_library_write(self.model.__name__)
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        _assert_library_write(self.model.__name__)
        return super().delete()

    def bulk_create(self, objs: Any, *args: Any, **kwargs: Any) -> Any:  # compliance: allow-kwargs Django QuerySet signature
        _assert_library_write(self.model.__name__)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs: Any, fields: Any, *args: Any, **kwargs: Any) -> Any:  # compliance: allow-kwargs Django QuerySet signature
        _assert_library_write(self.model.__name__)
        return super().bulk_update(objs, fields, *args, **kwargs)


class TenantModel(models.Model):
    """A row that belongs to one company (tenant zone). Every concrete subclass gets RLS
    enabled and forced by its migration through rls_operations()."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True


class LibraryModel(models.Model):
    """A sourced public fact shared by every tenant (library zone). No tenant_id. Changes
    only through approved proposals; the fence below and the AST guard make that true."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    objects = LibraryQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        _assert_library_write(type(self).__name__)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        _assert_library_write(type(self).__name__)
        return super().delete(*args, **kwargs)
