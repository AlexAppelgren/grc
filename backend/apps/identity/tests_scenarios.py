"""Scenario stubs for the identity app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ID.
"""

from unittest import skip

from django.test import TestCase


class IdentityScenarioTests(TestCase):
    """Scenario tests for apps.identity, one method per @integration scenario."""

    @skip("pending: ID-S1")
    def test_id_s1(self) -> None:
        """ID-S1

        An invitation carries roles and a single-use token that expires (ID-01).
        """

    @skip("pending: ID-S2")
    def test_id_s2(self) -> None:
        """ID-S2

        Opening the invitation sends a six-digit code within its limits (ID-02).
        """

    @skip("pending: ID-S3")
    def test_id_s3(self) -> None:
        """ID-S3

        A wrong code is refused and locks after five attempts (ID-02).
        """

    @skip("pending: ID-S4")
    def test_id_s4(self) -> None:
        """ID-S4

        The enrolment session reaches only passkey registration and GET /me (ID-02, AC-ID2).
        """

    @skip("pending: ID-S5")
    def test_id_s5(self) -> None:
        """ID-S5

        The first passkey activates the account and asks for a second one (ID-02, ID-03).
        """

    @skip("pending: ID-S6")
    def test_id_s6(self) -> None:
        """ID-S6

        A code request for an enrolled account looks normal and sends nothing (ID-03, AC-ID1).
        """

    @skip("pending: ID-S7")
    def test_id_s7(self) -> None:
        """ID-S7

        No password exists anywhere (ID-03).
        """

    @skip("pending: ID-S8")
    def test_id_s8(self) -> None:
        """ID-S8

        Passkey sign-in issues a session (ID-03).
        """

    @skip("pending: ID-S9")
    def test_id_s9(self) -> None:
        """ID-S9

        Refresh rotates and a replayed refresh is refused after the grace window (ID-03).
        """

    @skip("pending: ID-S10")
    def test_id_s10(self) -> None:
        """ID-S10

        A user adds and renames passkeys and can never remove the last one (ID-04).
        """

    @skip("pending: ID-S11")
    def test_id_s11(self) -> None:
        """ID-S11

        A user sees and revokes their sessions (ID-04).
        """

    @skip("pending: ID-S12")
    def test_id_s12(self) -> None:
        """ID-S12

        A tenant admin re-issues enrolment behind step-up (ID-05).
        """

    @skip("pending: ID-S13")
    def test_id_s13(self) -> None:
        """ID-S13

        The last admin recovers through platform support (ID-05).
        """

    @skip("pending: ID-S14")
    def test_id_s14(self) -> None:
        """ID-S14

        A sensitive action without a fresh assertion answers step_up_required (ID-06, AC-ID3).
        """

    @skip("pending: ID-S15")
    def test_id_s15(self) -> None:
        """ID-S15

        A completed sensitive action references its assertion on the audit event (ID-06, AC-ID3).
        """

    @skip("pending: ID-S16")
    def test_id_s16(self) -> None:
        """ID-S16

        A tenant can require attested device-bound authenticators (ID-07).
        """

    @skip("pending: ID-S17")
    def test_id_s17(self) -> None:
        """ID-S17

        Session limits are tenant policy within platform maximums (ID-08).
        """

    @skip("pending: ID-S18")
    def test_id_s18(self) -> None:
        """ID-S18

        Permissions are code and roles are rows (ID-09).
        """

    @skip("pending: ID-S19")
    def test_id_s19(self) -> None:
        """ID-S19

        A tenant always keeps one admin (ID-09).
        """

    @skip("pending: ID-S20")
    def test_id_s20(self) -> None:
        """ID-S20

        An API key is shown once, stored hashed and revocable (ID-10).
        """

    @skip("pending: ID-S21")
    def test_id_s21(self) -> None:
        """ID-S21

        No API key scope allows a library edit (ID-10, AC-PRO1).
        """

    @skip("pending: ID-S22")
    def test_id_s22(self) -> None:
        """ID-S22

        The security log records sign-ins, failures, enrolments, recoveries and key use (ID-11).
        """

    @skip("pending: ID-S23")
    def test_id_s23(self) -> None:
        """ID-S23

        SSO and SCIM never introduce a password (ID-12).
        """

    @skip("pending: ID-S24")
    def test_id_s24(self) -> None:
        """ID-S24

        A tenant IP allow-list blocks other addresses (ID-13).
        """

    @skip("pending: ID-S26")
    def test_id_s26(self) -> None:
        """ID-S26

        A denied request answers a structured 403 the UI renders as is (ID-09).
        """
