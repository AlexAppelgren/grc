"""The fixed logins of the E2E seed (playbook 8.3): one per system role in tenant A, tenant
B's admin, the platform editor and admin, and the one user still awaiting enrolment.
Plain data so both the seed (apps/shared/e2e_seed.py) and the key generator
(scripts/generate_e2e_passkeys.py) read one roster. Names come from the prototype's
USERS list where it has one (design/prototype/index.html)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedLogin:
    id: uuid.UUID
    email: str
    name: str
    tenant_slug: str | None  # None: platform staff
    tenant_roles: tuple[str, ...]
    platform_roles: tuple[str, ...] = ()
    title: str = ""
    has_passkey: bool = True
    awaiting_enrolment: bool = False
    # Under E2E_MODE, the plain token of an open invitation into `tenant_slug` that the seed
    # writes in place of a membership (hashed in the row). Empty: a member as seeded.
    invitation_token: str = ""
    locale: str = "en"  # the UI language every journey runs in (playbook 8.3: one pinned language)
    # The scenario IDs that alone may use this login, because they spend it (playbook 8.3
    # rule 4: what cannot be restored in a teardown gets a dedicated login). Empty: shared.
    reserved_for: tuple[str, ...] = ()


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-4000-8000-0000000001{n:02x}")


# E2E_MODE makes this the plain invitation token of the one awaiting user (hashed in the
# row). It opens the emailed-code path only; the mock mailer holds the code.
E2E_INVITATION_TOKEN_ANNA = "e2e-invite-anna"  # noqa: S105 an E2E fixture, not a credential
# D-122: the plain token of the bank invitation sent to a platform admin who already holds a
# passkey (ID-S39). The emailed code never opens for them; they join signed in.
E2E_INVITATION_TOKEN_JOINER = "e2e-invite-joiner"  # noqa: S105 an E2E fixture, not a credential

TENANT_A_SLUG = "example-bank"
TENANT_B_SLUG = "second-bank"

SEED_LOGINS: tuple[SeedLogin, ...] = (
    SeedLogin(_id(1), "admin@example-bank.test", "Erik Holm", TENANT_A_SLUG, ("admin",), title="Administrator"),
    SeedLogin(_id(2), "compliance_officer@example-bank.test", "Sara Lindqvist", TENANT_A_SLUG, ("compliance_officer",), title="Compliance officer"),
    SeedLogin(_id(3), "owner@example-bank.test", "Johan Berg", TENANT_A_SLUG, ("owner",), title="Obligation owner, digital investing"),
    SeedLogin(_id(4), "approver@example-bank.test", "Maria Ek", TENANT_A_SLUG, ("approver",), title="Approver, head of compliance"),
    SeedLogin(_id(5), "contributor@example-bank.test", "Karin Nyström", TENANT_A_SLUG, ("contributor",), title="Product specialist"),
    SeedLogin(_id(6), "reader@example-bank.test", "Oskar Lund", TENANT_A_SLUG, ("reader",), title="Legal counsel"),
    SeedLogin(_id(7), "auditor@example-bank.test", "Elin Sandberg", TENANT_A_SLUG, ("auditor",), title="Internal audit"),
    SeedLogin(
        _id(8),
        "anna@example-bank.test",
        "Anna Lindgren",
        TENANT_A_SLUG,
        ("compliance_officer", "reader"),
        title="Compliance officer",
        has_passkey=False,
        awaiting_enrolment=True,
        invitation_token=E2E_INVITATION_TOKEN_ANNA,
    ),
    SeedLogin(_id(9), "admin@second-bank.test", "Mette Jensen", TENANT_B_SLUG, ("admin",), title="Administrator"),
    SeedLogin(_id(10), "editor@bleqq.test", "Ida Holm", None, (), platform_roles=("library_editor",)),
    SeedLogin(_id(11), "platform@bleqq.test", "Per Ström", None, (), platform_roles=("platform_admin",)),
    # ADM-S2 changes this member's roles, revokes their sessions and re-issues their
    # enrolment. Re-issue cannot be undone through the UI, so it is spent on this login and
    # never on the approver, whom the footprint journeys (FP-S2, FP-S5) sign in as.
    SeedLogin(
        _id(12),
        "reissue@example-bank.test",
        "Lars Wikström",
        TENANT_A_SLUG,
        ("contributor",),
        title="Product specialist, payments",
        reserved_for=("ADM-S2",),
    ),
    # The second library editor. Four eyes holds in the console too (PRO-02, AC-PRO2): the
    # editor who files a proposal never decides it, so the queue journeys need a second one.
    SeedLogin(_id(13), "editor2@bleqq.test", "Kari Nygaard", None, (), platform_roles=("library_editor",)),
    # J-4's platform admin, who creates a platform agent key through the console under
    # `agent_definitions.manage` with a step-up. Not reserved: the key is revocable, so a run
    # never leaves this login unusable (and `reserved_for` assumes a tenant membership).
    SeedLogin(
        _id(14),
        "agent-keys@bleqq.test",
        "Sigrid Moen",
        None,
        (),
        platform_roles=("platform_admin",),
    ),
    # The one exception to "one pinned language": WAT-S2 reads the change page in Swedish as
    # a session whose `locale` is sv. Not reserved: it only reads, so a run never spends it;
    # its role is the shared "reader".
    SeedLogin(
        _id(15),
        "reader-sv@example-bank.test",
        "Astrid Sundqvist",
        TENANT_A_SLUG,
        ("reader",),
        title="Legal counsel",
        locale="sv",
    ),
    # I18N-S3's own login: the journey switches this member's language to sv and back, which
    # is saved on the person, so a login of its own keeps parallel journeys from rendering
    # in Swedish mid-run. It holds contributor, which no shared login stands for.
    SeedLogin(
        _id(16),
        "language@example-bank.test",
        "Nils Åberg",
        TENANT_A_SLUG,
        ("contributor",),
        title="Product specialist, cards",
        reserved_for=("I18N-S3",),
    ),
    # --- tax-market-journeys (FP-S8) --------------------------------------------------------
    # Tenant B's second person: FP-S8's Denmark request needs another approver (four eyes);
    # this one holds footprint.approve and not footprint.request.
    SeedLogin(_id(17), "approver@second-bank.test", "Freja Madsen", TENANT_B_SLUG, ("approver",), title="Approver, head of compliance"),
    # --- end tax-market-journeys -------------------------------------------------------------
    # --- r2-e2e-login-roster: every login the R2 journeys need, allocated once --------------
    # One numbered block, so parallel seed packages never collide on `_id(n)`. Each login is
    # reserved for the journeys that act on it, because each changes something the next run
    # must find as seeded (teams, absence, work, tokens).
    # Tenant A's head of Retail Banking: TEN-S8 makes them head, J-9 reads their department.
    SeedLogin(_id(18), "head@example-bank.test", "Karin Ek", TENANT_A_SLUG, ("owner",), title="Head of Retail Banking", reserved_for=("HOM-S13", "TEN-S8")),
    # J-9's contributor: added as a participant, then leaves.
    SeedLogin(_id(19), "participant@example-bank.test", "Viktor Hedlund", TENANT_A_SLUG, ("contributor",), title="Product specialist, savings", reserved_for=("HOM-S13",)),
    # TEN-S5 removes this member, who owns obligations and open cases, and reassigns the work.
    SeedLogin(_id(20), "leaver@example-bank.test", "Gustav Sjöberg", TENANT_A_SLUG, ("owner",), title="Obligation owner, savings", reserved_for=("TEN-S5",)),
    # TEN-S8 puts this member in a team.
    SeedLogin(_id(21), "teams@example-bank.test", "Linnea Forsberg", TENANT_A_SLUG, ("contributor",), title="Product specialist, lending", reserved_for=("TEN-S8",)),
    # TEN-S4: the approver who goes out of office with a delegate. The shared approver is the
    # delegate, so nothing about their own absence leaks into another journey.
    SeedLogin(_id(22), "away@example-bank.test", "Henrik Wallin", TENANT_A_SLUG, ("approver",), title="Approver, deputy head of compliance", reserved_for=("TEN-S4",)),
    # CAS-S9 and J-3: the owner who also holds cases.signoff, refused on their own case.
    SeedLogin(_id(23), "owner-approver@example-bank.test", "Emma Lindberg", TENANT_A_SLUG, ("owner", "approver"), title="Obligation owner and approver, payments", reserved_for=("CAS-S9", "CAS-S15")),
    # COL-S2: the Swedish-speaking team member whose reminders arrive in sv.
    SeedLogin(_id(24), "sv-member@example-bank.test", "Ingrid Bergström", TENANT_A_SLUG, ("owner",), title="Obligation owner, pensions", locale="sv", reserved_for=("COL-S2",)),
    # ACC-S11: the second member holding security.manage, so tenant reach keeps four eyes.
    SeedLogin(_id(25), "security@example-bank.test", "Magnus Öberg", TENANT_A_SLUG, ("admin",), title="Administrator, information security", reserved_for=("ACC-S11", "ACC-S13")),
    # ACC-S3: the compliance officer who mints a personal access token.
    SeedLogin(_id(26), "tokens@example-bank.test", "Elsa Hansson", TENANT_A_SLUG, ("compliance_officer",), title="Compliance officer, reporting", reserved_for=("ACC-S3",)),
    # HOM-S10, COL-S12 and COL-S8: a member whose one role reads neither the register nor
    # cases (NO_RECORD_READ_ROLE, a tenant role e2e_seed.py creates before the logins).
    SeedLogin(_id(27), "library-only@example-bank.test", "Axel Norén", TENANT_A_SLUG, ("library_only",), title="Trainee, compliance", reserved_for=("HOM-S10", "COL-S12", "COL-S8")),
    # Tenant B's compliance officer: J-2 triages tenant B's own lead, and J-8 signs in as them.
    SeedLogin(_id(28), "compliance_officer@second-bank.test", "Søren Kristensen", TENANT_B_SLUG, ("compliance_officer",), title="Compliance officer", reserved_for=("CAS-S14", "TEN-S7")),
    # --- end r2-e2e-login-roster -------------------------------------------------------------
    # D-122: one account that is a bank's member and platform staff. ID-S34 switches it from
    # the bank to the console and back with a passkey; ID-S37 reads its marker on Members.
    # Reserved, because a switch revokes the session it leaves.
    SeedLogin(
        _id(29),
        "dual@example-bank.test",
        "Alva Strand",
        TENANT_A_SLUG,
        ("contributor",),
        platform_roles=("platform_admin",),
        title="Product specialist and platform administrator",
        reserved_for=("ID-S34", "ID-S37"),
    ),
    # D-122: a platform admin with a passkey and no bank, invited into tenant B as a reader.
    # ID-S39 proves the code sends nothing, then signs in, joins with a step-up and switches
    # into tenant B. Reserved, because joining makes them a member for the rest of the run.
    SeedLogin(
        _id(30),
        "joiner@second-bank.test",
        "Nora Falk",
        TENANT_B_SLUG,
        ("reader",),
        platform_roles=("platform_admin",),
        title="Platform administrator",
        invitation_token=E2E_INVITATION_TOKEN_JOINER,
        reserved_for=("ID-S39",),
    ),
    # D-135: a member who lets a second browser in with its code and creates a passkey there.
    # Reserved, because the passkey the second browser creates stays on the account.
    SeedLogin(_id(31), "devices@example-bank.test", "Tove Nyberg", TENANT_A_SLUG, ("reader",), title="Compliance analyst", reserved_for=("ID-S40",)),
)

# The login ADM-S2 spends (above). Named here so the guard and the journey read one value.
REISSUE_LOGIN_EMAIL = "reissue@example-bank.test"

# The platform role a proposal decision needs on two people at once (four eyes, PRO-02).
LIBRARY_EDITOR_ROLE = "library_editor"

# --- r2-e2e-login-roster ---------------------------------------------------------------------
# The first and last `_id(n)` of the roster above, and the tenant role the no-record-read
# login holds: every permission but register.read and cases.read.
R2_ROSTER_IDS = range(18, 29)
NO_RECORD_READ_ROLE = "library_only"
# --- end r2-e2e-login-roster -----------------------------------------------------------------
