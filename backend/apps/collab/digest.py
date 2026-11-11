"""The weekly digest (COL-02, HOM-05): one mail per person per week listing their open items
as My work counts them.

- One definition: the content is `home/my_work.py`'s answer for the reader's own scope
  (D-23); this module reads no case, action or entry itself, which a test pins.
- The reader's own: their roles, their language, to them alone; never to a delegate,
  escalated or copied (TEN-04).
- At most `DIGEST_MAX_ITEMS` rows, the most urgent, then "and N more".
- Only titles, counts, dates and links: catalog strings filled from a `MailContext`, links
  under `APP_BASE_URL` with no token.
- Once a week: `tasks.deliver_mail` composes it in the worker (no title rides the queue) and
  keys its `email_message` row to the bank's week. Nothing open, no mail.

`send_all()` is what the weekly beat calls for one bank.
"""

from __future__ import annotations

import datetime

from django.conf import settings

from apps.collab import mail
from apps.home import my_work
from apps.home.schemas import HomeWorkItem, HomeWorkPage, HomeWorkQuery
from apps.identity import roles_logic
from apps.identity.models import Membership, UserStatus
from apps.identity.schemas import MembershipNotificationPrefs
from apps.library.reading import today_for
from apps.shared.adapters.mailer import OutgoingMail
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.permissions import TENANT_PERMISSIONS

TEMPLATE: mail.Template = "weekly_digest"
# The catalog keys of the sections: a heading per bucket, a row, and the rows left out.
SECTION_KEYS: tuple[str, ...] = (
    *(f"{TEMPLATE}.{bucket}" for bucket in my_work.BUCKETS),
    f"{TEMPLATE}.item",
    f"{TEMPLATE}.more",
)


def week_of(day: datetime.date) -> datetime.date:
    """The first day, a Monday, of the week `day` falls in: the key of that week's digest."""
    return day - datetime.timedelta(days=day.weekday())


def _url(path: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/{path}"


def _link(item: HomeWorkItem) -> str:
    """The row's own page: an obligation's, or the change page that holds a bank's case. An
    internal item has no page of its own, so its row links to My work, where it is listed."""
    subject = item.subject
    if subject.obligation_id:
        return _url(f"inventory/obligations/{subject.obligation_id}")
    if subject.change_id:
        return _url(f"watch/{subject.change_id}")
    return _url("work")


def content(membership: Membership) -> HomeWorkPage | None:
    """My work for the member as they would read it themself, at most `DIGEST_MAX_ITEMS`
    rows; None when nothing is open. Runs in the activated tenant."""
    tenant, user = membership.tenant, membership.user
    principal = Principal(
        kind=PrincipalKind.USER,
        subject_id=user.id,
        tenant_id=tenant.id,
        # A session's own rule: the roles' grants, of the bank's permissions only.
        permissions=roles_logic.permissions_of(membership.roles.all()) & TENANT_PERMISSIONS,
    )
    page = my_work.page(
        tenant,
        principal,
        roles_logic.language_order(user, tenant),
        HomeWorkQuery(limit=settings.DIGEST_MAX_ITEMS),
    )
    return page if page.total else None


def _summary(membership: Membership, page: HomeWorkPage) -> mail.MailContext:
    return mail.MailContext(date=today_for(membership.tenant), count=page.total, link=_url("work"))


def compose(membership: Membership) -> OutgoingMail | None:
    """The member's digest as it stands now, in their language, or None when nothing is
    open: a heading and the rows of each bucket that has any, then what the cap left out."""
    page = content(membership)
    if page is None:
        return None
    sections: list[list[tuple[str, mail.MailContext]]] = []
    for bucket in my_work.BUCKETS:
        count = getattr(page.counts, bucket)
        if count:
            sections.append(
                [
                    (f"{TEMPLATE}.{bucket}", mail.MailContext(count=count)),
                    *(
                        (
                            f"{TEMPLATE}.item",
                            mail.MailContext(title=item.subject.title, link=_link(item)),
                        )
                        for item in page.items
                        if item.bucket == bucket
                    ),
                ]
            )
    if page.total > len(page.items):
        sections.append(
            [(f"{TEMPLATE}.more", mail.MailContext(count=page.total - len(page.items)))]
        )
    return mail.compose(membership, TEMPLATE, _summary(membership, page), sections=sections)


def send(membership: Membership) -> None:
    """Queue the member's digest, unless they switched it off or nothing is open."""
    if not MembershipNotificationPrefs.model_validate(membership.notification_prefs).weekly_digest:
        return
    page = content(membership)
    if page is None:
        return
    mail.send(membership, TEMPLATE, _summary(membership, page), subject_type=None, subject_id=None)


def send_all() -> None:
    """Every active member's digest in the activated tenant, each their own."""
    members = (
        Membership.objects.filter(deactivated_at__isnull=True, user__status=UserStatus.ACTIVE.value)
        .select_related("user__locale", "tenant__default_language")
        .order_by("user_id")
    )
    for membership in members:
        send(membership)
