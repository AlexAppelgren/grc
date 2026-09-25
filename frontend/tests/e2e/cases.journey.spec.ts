import { test } from './support/api-guard';

// cases: the @e2e scenarios from backend/apps/cases/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('cases journeys', () => {
  test.fixme("CAS-S2: Triage needs an urgency and an owner", async () => {
    // pending: CAS-S2 (CAS-02)
  });

  test.fixme("CAS-S3: Dismissal needs a reason and can be restored", async () => {
    // pending: CAS-S3 (CAS-02)
  });

  test.fixme("CAS-S4: The impact assessment records what applies and what must change", async () => {
    // pending: CAS-S4 (CAS-03)
  });

  test.fixme("CAS-S6: Actions have an owner and due date, lock during sign-off and export as tickets", async () => {
    // pending: CAS-S6 (CAS-04)
  });

  test.fixme("CAS-S7: Evidence is scanned, hashed and streamed through permission checks", async () => {
    // pending: CAS-S7 (CAS-05)
  });

  test.fixme("CAS-S8: Sign-off is refused while actions are open or evidence is missing", async () => {
    // pending: CAS-S8 (CAS-06, AC-CAS1)
  });

  test.fixme("CAS-S9: The requester cannot sign off their own case", async () => {
    // pending: CAS-S9 (CAS-06, AC-CAS1)
  });

  test.fixme("CAS-S10: A second person signs off with step-up and the inventory is untouched", async () => {
    // pending: CAS-S10 (CAS-06)
  });

  test.fixme("CAS-S11: The case file stands alone as text and as an export", async () => {
    // pending: CAS-S11 (CAS-07)
  });

  test.fixme("CAS-S14 J-2 @smoke: from Today to a triaged case", async () => {
    // pending: CAS-S14 (CAS-01, CAS-02, WAT-05, HOM-01, J-2)
  });

  test.fixme("CAS-S15 J-3 @smoke: assessment to sign-off and the case file", async () => {
    // pending: CAS-S15 (CAS-03, CAS-04, CAS-05, CAS-06, CAS-07, AC-CAS1, J-3)
  });

  // c9-triage: the API is built; the panel is c9-fe-triage-panel's and the walk c9-e2e-triage-journeys'.
  test.fixme("CAS-S19: One person closes a case that needs no work, audited, and can restore it", async () => {
    // pending: CAS-S19 (CAS-02)
  });
});
