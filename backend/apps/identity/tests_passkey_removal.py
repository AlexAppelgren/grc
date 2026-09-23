"""Two removals of one person's passkeys at once take turns (ID-04, ID-05).

A person may never remove their last passkey, so re-enrolment is the only thing that leaves
them with none, and the calendar feed reads that moment as one (`home/feed.py`). Counted
without a lock, two removals of a person's last two passkeys would each see the other's as
the one left, and both would go. Proved with two connections rather than two threads: the
application role holds the row a concurrent removal has just retired, and a removal of the
other passkey is shown to wait for it rather than count it as still there.
"""

from __future__ import annotations

from django.db import DEFAULT_DB_ALIAS, OperationalError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.identity import passkey_logic
from apps.identity.models import WebAuthnCredential
from apps.shared import factories
from apps.shared.testing import user_principal


class TwoRemovalsAtOnceTakeTurns(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def test_a_removal_waits_for_one_already_retiring_the_other_passkey(self) -> None:
        person = factories.user()
        phone = factories.passkey(person, nickname="Phone")
        laptop = factories.passkey(person, nickname="Laptop")
        with transaction.atomic(using="app"):
            # The laptop's removal, retired and not yet committed.
            WebAuthnCredential.objects.using("app").filter(pk=laptop.pk).update(retired_at=timezone.now())
            with self.assertRaisesMessage(OperationalError, "lock timeout"), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '200ms'")
                passkey_logic.remove_passkey(user_principal(subject_id=person.id), phone.id)
            transaction.set_rollback(True, using="app")
        phone.refresh_from_db()
        self.assertIsNone(phone.retired_at, "the waiting removal retired nothing")
