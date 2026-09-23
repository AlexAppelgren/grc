"""Shared routes (playbook 4.1: routes only): `GET /reference/product` (bootstrap) and the
E2E-only mail outbox. `/me` moved to the identity app in chunk 1.

Each route's docstring is its published `description` (django-ninja reads it), written for
an integrator at a bank who has never seen this codebase, to the standard in
`docs/plans/briefs/API_DOCUMENTATION.md`.
"""

from django.http import HttpRequest
from ninja import Router

from apps.shared import logic
from apps.shared.schemas import MailOutboxMessage, ProductInfo

router = Router(tags=["Shared"])

# Static on purpose: an example is read, never computed, so an operator's own code lifetime
# or base URL never changes the exported contract. The addresses are the seeded example bank.
_MAIL_OUTBOX_EXAMPLE = {
    "responses": {
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "to": "new.member@example-bank.test",
                            "subject": "You are invited to Example Bank AB",
                            "body": (
                                "You have been invited to Example Bank AB on Compliance Watch.\n"
                                "Open this link within 72 hours to receive your code: "
                                "http://localhost:3000/invite#example-invitation-token"
                            ),
                        },
                        {
                            "to": "new.member@example-bank.test",
                            "subject": "Your Compliance Watch sign-in code",
                            "body": "Your code is 123456. It works once and expires in 10 minutes.",
                        },
                    ]
                }
            }
        }
    }
}


@router.get(
    "/reference/product",
    response=ProductInfo,
    auth=None,
    operation_id="getProduct",
    by_alias=True,
    summary="Read the product's name before anyone has signed in",
)
def get_product(request: HttpRequest) -> ProductInfo:
    """Returns the name this deployment of the product goes by. Call it when a screen needs
    the name before any session exists, such as a sign-in page, so it shows the name the
    operator configured for this deployment rather than one built into the client; the
    same name is what a passkey prompt shows as the service the passkey belongs to.

    No credential is needed and none is read: the answer is the same for every caller,
    says nothing about any bank or person, and is safe to keep for the life of a page. It
    changes nothing and writes nothing to the audit log. The call takes no input, so there
    is no error for a caller to branch on.
    """
    # Ungated by design: `bootstrap`. The sign-in page shows the product name first.
    return logic.product_info()


@router.get(
    "/e2e/mail-outbox",
    response=list[MailOutboxMessage],
    auth=None,
    operation_id="e2eMailOutbox",
    by_alias=True,
    summary="Read the mail a test run sent (test environments only)",
    openapi_extra=_MAIL_OUTBOX_EXAMPLE,
)
def e2e_mail_outbox(request: HttpRequest) -> list[MailOutboxMessage]:
    """For automated end-to-end test runs only. Returns every message the stand-in mailer
    has sent since the outbox was last cleared, oldest first, so a test journey can read
    the enrolment code or invitation link a real person would find in their inbox, and can
    prove that a code request for someone who already has a passkey sent nothing.

    The route exists only when the server runs in end-to-end test mode (`E2E_MODE`) with
    the stand-in mailer. Every deployed environment refuses to boot with that mode on, so
    against a real bank's deployment this call always answers `not_found`, exactly like a
    path that does not exist, and no mail ever sent there can be read back through it. It
    stays in the published contract only so the test suite's client is typed against it;
    an integrator never calls it.

    No credential is needed: the test mode is the whole gate. It changes nothing, writes
    nothing to the audit log and does not page, because a test run sends a handful of
    messages. An empty outbox is a 200 with an empty list.

    Errors: `not_found` whenever end-to-end test mode or the stand-in mailer is off, which
    is always the case when deployed.
    """
    # Ungated by design: `bootstrap`. Answers 404 unless E2E_MODE is on (playbook 8.3).
    return logic.mail_outbox()
