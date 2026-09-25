"""The case state machine, table-driven (CAS-02, CAS-06, CAS-08; c9-state-machine).

Every ordered pair of categories, allowed or not; every guard, held and broken, with the
code its refusal carries; `allowed_transitions` total over the seven categories; and the
module's imports, so a later task cannot hide a query in it.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
import sys
import uuid
from itertools import product
from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase

from apps.cases import state
from apps.cases.state import CaseFacts, InvalidTransition
from apps.shared.kinds import CaseStatusCategory as C
from apps.shared.kinds import CloseReason

REQUESTER = uuid.uuid4()
SECOND_PERSON = uuid.uuid4()

# The machine as the brief draws it, written out here and not read from the module, so a
# changed table fails this test instead of agreeing with itself.
EDGES = {
    (C.NEW, C.ASSIGNED),
    (C.NEW, C.DISMISSED),
    (C.DISMISSED, C.NEW),
    (C.ASSIGNED, C.ASSESSING),
    (C.ASSIGNED, C.CLOSED),
    (C.ASSESSING, C.IMPLEMENTING),
    (C.ASSESSING, C.CLOSED),
    (C.IMPLEMENTING, C.SIGNOFF),
    (C.SIGNOFF, C.IMPLEMENTING),
    (C.SIGNOFF, C.CLOSED),
    (C.CLOSED, C.NEW),
}

# Every guard holds: an owner named, a reason given, a why saved, no open action, one clean
# evidence, a second person, and a close reason one person may choose.
HELD = CaseFacts(
    owner_set=True,
    reason_given=True,
    why_saved=True,
    open_action_count=0,
    clean_evidence_count=1,
    signoff_requester=REQUESTER,
    actor=SECOND_PERSON,
    close_reason_kind=CloseReason.NO_ACTION,
)

# (edge, the fact that breaks the guard, the code the refusal carries)
BROKEN_GUARDS: list[tuple[tuple[C, C], dict[str, object], str]] = [
    ((C.NEW, C.ASSIGNED), {"owner_set": False}, "owner_required"),
    ((C.NEW, C.DISMISSED), {"reason_given": False}, "reason_required"),
    ((C.ASSESSING, C.IMPLEMENTING), {"why_saved": False}, "why_required"),
    ((C.IMPLEMENTING, C.SIGNOFF), {"open_action_count": 1}, "open_actions"),
    ((C.IMPLEMENTING, C.SIGNOFF), {"clean_evidence_count": 0}, "evidence_missing"),
    ((C.SIGNOFF, C.CLOSED), {"actor": REQUESTER}, "four_eyes_violation"),
    ((C.SIGNOFF, C.CLOSED), {"signoff_requester": None}, "four_eyes_violation"),
    ((C.SIGNOFF, C.CLOSED), {"actor": None}, "four_eyes_violation"),
    ((C.ASSIGNED, C.CLOSED), {"close_reason_kind": None}, "reason_required"),
    ((C.ASSIGNED, C.CLOSED), {"close_reason_kind": CloseReason.SIGNED_OFF}, "four_eyes_violation"),
    ((C.ASSESSING, C.CLOSED), {"close_reason_kind": None}, "reason_required"),
    ((C.ASSESSING, C.CLOSED), {"close_reason_kind": CloseReason.SIGNED_OFF}, "four_eyes_violation"),
    ((C.CLOSED, C.NEW), {"close_reason_kind": CloseReason.SIGNED_OFF}, "invalid_transition"),
    ((C.CLOSED, C.NEW), {"close_reason_kind": None}, "invalid_transition"),
]


def facts(**changes: object) -> CaseFacts:
    return dataclasses.replace(HELD, **changes)  # type: ignore[arg-type]


def refusal_code(from_status: C, to_status: C, case_facts: CaseFacts) -> str | None:
    try:
        state.check_transition(from_status, to_status, case_facts)
    except InvalidTransition as refusal:
        return refusal.code
    return None


class TransitionTableTests(SimpleTestCase):
    def test_all_49_ordered_pairs_are_allowed_exactly_when_the_diagram_draws_them(self) -> None:
        pairs = list(product(C, C))
        self.assertEqual(len(pairs), 49)
        for from_status, to_status in pairs:
            with self.subTest(pair=f"{from_status}->{to_status}"):
                drawn = (from_status, to_status) in EDGES
                self.assertEqual(to_status in state.TRANSITIONS[from_status], drawn)
                code = refusal_code(from_status, to_status, HELD)
                self.assertEqual(code, None if drawn else "invalid_transition")

    def test_the_table_names_every_category_and_nothing_else(self) -> None:
        self.assertEqual(set(state.TRANSITIONS), set(C))
        for targets in state.TRANSITIONS.values():
            self.assertTrue(set(targets) <= set(C))

    def test_every_guard_sits_on_a_drawn_edge(self) -> None:
        self.assertTrue(set(state.GUARDS) <= EDGES)


class GuardTests(SimpleTestCase):
    def test_each_guard_refuses_with_its_own_code_when_broken(self) -> None:
        for (from_status, to_status), change, code in BROKEN_GUARDS:
            with self.subTest(edge=f"{from_status}->{to_status}", change=change):
                self.assertEqual(refusal_code(from_status, to_status, facts(**change)), code)

    def test_each_guard_lets_the_move_through_when_it_holds(self) -> None:
        for (from_status, to_status), _change, _code in BROKEN_GUARDS:
            with self.subTest(edge=f"{from_status}->{to_status}"):
                self.assertIsNone(refusal_code(from_status, to_status, HELD))

    def test_either_close_reason_one_person_may_choose_closes_and_reopens(self) -> None:
        for kind in (CloseReason.NO_ACTION, CloseReason.NOT_APPLICABLE):
            with self.subTest(kind=kind):
                one_person = facts(close_reason_kind=kind)
                self.assertIsNone(refusal_code(C.ASSIGNED, C.CLOSED, one_person))
                self.assertIsNone(refusal_code(C.ASSESSING, C.CLOSED, one_person))
                self.assertIsNone(refusal_code(C.CLOSED, C.NEW, one_person))

    def test_a_sign_off_close_needs_no_close_reason_from_the_facts(self) -> None:
        self.assertIsNone(refusal_code(C.SIGNOFF, C.CLOSED, facts(close_reason_kind=CloseReason.SIGNED_OFF)))

    def test_every_guard_is_named_and_carries_a_code(self) -> None:
        for edge, guards in state.GUARDS.items():
            for guard in guards:
                with self.subTest(edge=edge, guard=guard.name):
                    self.assertRegex(guard.name, r"^[a-z_]+$")
                    self.assertIn(guard.code, state.REFUSAL_CODES)

    def test_every_guard_holds_on_held_facts(self) -> None:
        for guards in state.GUARDS.values():
            for guard in guards:
                with self.subTest(guard=guard.name):
                    self.assertTrue(guard.holds(HELD))


class AllowedTransitionsTests(SimpleTestCase):
    def test_allowed_transitions_is_total(self) -> None:
        for category in C:
            with self.subTest(category=category):
                allowed = state.allowed_transitions(category, HELD)
                self.assertIsInstance(allowed, list)
                self.assertEqual(set(allowed), {to for (fr, to) in EDGES if fr == category})

    def test_the_move_supplies_what_a_read_cannot_know(self) -> None:
        # A fresh case has no owner and no reason yet: triage and dismissal name them.
        unknown = facts(owner_set=False, reason_given=False, close_reason_kind=None)
        self.assertEqual(set(state.allowed_transitions(C.NEW, unknown)), {C.ASSIGNED, C.DISMISSED})
        self.assertEqual(set(state.allowed_transitions(C.ASSIGNED, unknown)), {C.ASSESSING, C.CLOSED})

    def test_the_case_guards_filter_what_a_read_lists(self) -> None:
        self.assertEqual(state.allowed_transitions(C.ASSESSING, facts(why_saved=False)), [C.CLOSED])
        self.assertEqual(state.allowed_transitions(C.IMPLEMENTING, facts(open_action_count=2)), [])
        self.assertEqual(state.allowed_transitions(C.IMPLEMENTING, facts(clean_evidence_count=0)), [])
        self.assertEqual(state.allowed_transitions(C.SIGNOFF, facts(actor=REQUESTER)), [C.IMPLEMENTING])
        self.assertEqual(state.allowed_transitions(C.CLOSED, facts(close_reason_kind=CloseReason.SIGNED_OFF)), [])
        self.assertEqual(
            state.allowed_transitions(C.CLOSED, facts(close_reason_kind=CloseReason.NOT_APPLICABLE)), [C.NEW]
        )

    def test_is_open_is_false_only_for_closed_and_dismissed(self) -> None:
        for category in C:
            with self.subTest(category=category):
                self.assertEqual(state.is_open(category), category not in (C.CLOSED, C.DISMISSED))


class RefusalShapeTests(SimpleTestCase):
    def test_a_refusal_is_a_validation_error_with_a_code_and_words(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            state.check_transition(C.NEW, C.CLOSED, HELD)
        self.assertEqual(caught.exception.code, "invalid_transition")
        self.assertTrue(caught.exception.messages[0])

    def test_every_refusal_renders_as_problem_details_with_its_code(self) -> None:
        from config.api import handle_django_validation

        request = RequestFactory().post("/api/v1/cases")
        for (from_status, to_status), change, code in BROKEN_GUARDS:
            with self.subTest(code=code, edge=f"{from_status}->{to_status}"):
                with self.assertRaises(InvalidTransition) as caught:
                    state.check_transition(from_status, to_status, facts(**change))
                response = handle_django_validation(request, caught.exception)
                self.assertEqual(response["Content-Type"], "application/problem+json")
                body = json.loads(response.content)
                self.assertEqual(body["code"], code)
                self.assertNotIn("Traceback", body["detail"])

    def test_the_facts_are_frozen(self) -> None:
        with self.assertRaises(dataclasses.FrozenInstanceError):
            HELD.owner_set = False  # type: ignore[misc]


class PurityTests(SimpleTestCase):
    source = Path(state.__file__)

    def test_the_module_imports_no_orm_and_no_models(self) -> None:
        tree = ast.parse(self.source.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        self.assertEqual(
            imported,
            {"__future__", "collections.abc", "dataclasses", "uuid", "django.core.exceptions", "apps.shared.kinds"},
        )

    def test_importing_the_module_loads_no_database_code(self) -> None:
        probe = (
            "import sys; import apps.cases.state; "
            "loaded = sorted(m for m in sys.modules if m.startswith('django.db') or m.endswith('.models')); "
            "print(','.join(loaded))"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=self.source.parents[2],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "")
