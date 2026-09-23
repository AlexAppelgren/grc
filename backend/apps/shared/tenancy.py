"""Tenancy and the two zones (playbook 14).

- `clear_tenant()` and `platform_zone()` leave the tenant zone, for the rest of the
  transaction or for a block, which is how a request with no tenant runs and how a tenant's
  own session writes a row that belongs to no tenant (an audit row about a library record,
  say): since H15 a mixed table accepts only the zone the session is in. The tenancy guard
  pins who may call them.
- `activate(tenant_id)` issues `SET LOCAL app.tenant_id` (through `set_config(..., true)`,
  which is the parameterised spelling) inside the open transaction. Policies read
  `current_setting('app.tenant_id', true)`, so an unset value matches no rows. It refuses
  to run outside a transaction because `SET LOCAL` outside one is a silent no-op and the
  request would then see nothing and write nothing, or worse under a bypassing role.
- `@tenant_task` wraps a Celery task body: the tenant id is the explicit first argument
  and the task activates it inside its own transaction.
- `TenantModel`: abstract, `tenant` FK, sits under forced RLS (the migration helper in
  apps/shared/migration_helpers.py writes the policy; the RLS guard checks it exists).
- `LibraryModel`: abstract, no tenant. Writes are refused outside `library_write()`, and
  the library-fence guard restricts `library_write()` to the modules that apply approved
  proposals, the watch pipeline and reference seeds (PRO-01, playbook 5).
- `library_door()` is the database's half of that fence (H16, ADR 0058): it names the door
  a write comes through in a transaction-local setting, and a trigger on every library-zone
  table (shared 0008) refuses a write from the app role whose door that table does not
  accept. `library_write()` and the index door open it; nothing else may.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal, TypeVar

from django.db import DEFAULT_DB_ALIAS, connections, models, transaction

TENANT_SETTING = "app.tenant_id"
# The identity-lookup flag (chunk 1). Five tables are read before any tenant is known: an
# invitation by its token or address, a membership at passkey sign-in (to pick the
# session's tenant), a session by its refresh cookie, an API key by its prefix, and a
# calendar subscription by the prefix in its address, which is the one credential that
# arrives with no session and no key at all (D-52, ADR 0045).
# Their policies add `OR current_setting('app.identity_lookup', true) = 'on'`, and
# `identity_lookup()` below switches the flag on for the shortest possible block, then
# clears it. The RLS guard lists exactly which tables carry the clause
# (apps/shared/tests_rls.py, IDENTITY_LOOKUP_TABLES) and an AST guard restricts callers
# to apps/shared/authentication.py and the identity app's logic modules.
IDENTITY_LOOKUP_SETTING = "app.identity_lookup"
# The door a library-zone write comes through (H16, ADR 0058). The trigger shared 0008
# puts on every library-zone table reads it and refuses a write from the app role unless it
# names a door that table accepts: `proposal` and `seed` the inventory and the library
# vocabularies, `reverification` the obligation and its verification rows only, `watch` the
# seven watch tables only (D-64) and `index` the search index only (D-65). The compliance
# lint's `library-door` rule keeps this name in this module, the index door, the migration
# helpers, migrations and tests.
LIBRARY_DOOR_SETTING = "cw.library_door"
LibraryDoor = Literal["proposal", "reverification", "seed", "watch", "index"]

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
    """Leave the tenant zone for the rest of the transaction: the session is then in the
    zone of the rows that belong to no tenant, which is where a request with no tenant runs
    in production. `platform_zone()` below is the block form, and the tenancy guard pins who
    may call either."""
    connection = connections[using]
    if not connection.in_atomic_block:
        raise NotInTransaction("tenancy.clear_tenant() needs an open transaction: SET LOCAL is a no-op outside one.")
    _set_tenant_setting("", using=using)
    _active_tenant.set(None)


@contextmanager
def platform_zone(*, using: str = DEFAULT_DB_ALIAS) -> Iterator[None]:
    """Write rows that belong to no tenant, inside the open transaction, then put the
    session's tenant back.

    Since the write rules were split (H15) a mixed table accepts only the rows of the zone
    the session is in, so a platform row cannot be written while a tenant is activated. Most
    platform work never activates one; the exceptions are the actions a bank's own session
    takes whose subject belongs to the library or the console, and `record()` writes their
    audit row here. A block that raises leaves the tenant as it found it.
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


@contextmanager
def identity_lookup(*, using: str = DEFAULT_DB_ALIAS) -> Iterator[None]:
    """Read identity rows of any tenant for the duration of the block, inside the open
    transaction, then switch the flag off again. Only the auth layer may use it."""
    connection = connections[using]
    if not connection.in_atomic_block:
        raise NotInTransaction("tenancy.identity_lookup() needs an open transaction: SET LOCAL is a no-op outside one.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [IDENTITY_LOOKUP_SETTING, "on"])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, true)", [IDENTITY_LOOKUP_SETTING, ""])


def identity_lookup_active(*, using: str = DEFAULT_DB_ALIAS) -> bool:
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [IDENTITY_LOOKUP_SETTING])
        row = cursor.fetchone()
    return bool(row and row[0] == "on")


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


def is_tenant_task(fn: Callable[..., Any]) -> bool:
    return bool(getattr(fn, "__cw_tenant_task__", False))


# ---------------------------------------------------------------------------------------
# Library fence
# ---------------------------------------------------------------------------------------
@contextmanager
def library_write(reason: str, *, door: LibraryDoor = "seed") -> Iterator[None]:
    """The only context in which a LibraryModel may be saved or deleted. `reason` names the
    proposal, the watch step or the seed; it is recorded by record() callers.

    `door` is what the database is told (H16, ADR 0058): the proposal applier names
    `proposal` or `reverification` and the watch door `watch`; a reference seed and a test
    builder take the default. Which module may name which door is pinned by the library
    fence (apps/shared/tests_library_fence.py)."""
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

    The setting is transaction-local, so the block runs in a transaction: its own when none
    is open, a savepoint inside one. A door set in autocommit would be gone by the next
    statement and the write after it refused. On the way out the door it found is put back,
    so doors nest (a proposal's approval opens the index door for its rebuild); a block that
    raises rolls its savepoint back, and PostgreSQL undoes the setting with it. `using`
    exists for the guard, which proves the trigger on the cw_app alias."""
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            cursor.execute("SELECT coalesce(current_setting(%s, true), '')", [LIBRARY_DOOR_SETTING])
            row = cursor.fetchone()
            cursor.execute("SELECT set_config(%s, %s, true)", [LIBRARY_DOOR_SETTING, door])
        yield
        with connections[using].cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, true)", [LIBRARY_DOOR_SETTING, row[0] if row else ""])


def library_write_reason() -> str | None:
    return _library_write_reason.get()


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
