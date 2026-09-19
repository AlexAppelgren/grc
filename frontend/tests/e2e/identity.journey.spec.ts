import { test } from './support/api-guard';

// identity: the @e2e scenarios from backend/apps/identity/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('identity journeys', () => {
  test.fixme("ID-S4: The enrolment session reaches only passkey registration and GET /me", async () => {
    // pending: ID-S4 (ID-02, AC-ID2)
  });

  test.fixme("ID-S5: The first passkey activates the account and asks for a second one", async () => {
    // pending: ID-S5 (ID-02, ID-03)
  });

  test.fixme("ID-S6: A code request for an enrolled account looks normal and sends nothing", async () => {
    // pending: ID-S6 (ID-03, AC-ID1)
  });

  test.fixme("ID-S8: Passkey sign-in issues a session", async () => {
    // pending: ID-S8 (ID-03)
  });

  test.fixme("ID-S10: A user adds and renames passkeys and can never remove the last one", async () => {
    // pending: ID-S10 (ID-04)
  });

  test.fixme("ID-S11: A user sees and revokes their sessions", async () => {
    // pending: ID-S11 (ID-04)
  });

  test.fixme("ID-S12: A tenant admin re-issues enrolment behind step-up", async () => {
    // pending: ID-S12 (ID-05)
  });

  test.fixme("ID-S14: A sensitive action without a fresh assertion answers step_up_required", async () => {
    // pending: ID-S14 (ID-06, AC-ID3)
  });

  test.fixme("ID-S18: Permissions are code and roles are rows", async () => {
    // pending: ID-S18 (ID-09)
  });

  test.fixme("ID-S20: An API key is shown once, stored hashed and revocable", async () => {
    // pending: ID-S20 (ID-10)
  });

  test.fixme("ID-S25 J-1 @smoke: invitation to passkey sign-in", async () => {
    // pending: ID-S25 (ID-01, ID-02, ID-03, AC-ID1, J-1)
  });

  test.fixme("ID-S26: A denied request answers a structured 403 the UI renders as is", async () => {
    // pending: ID-S26 (ID-09)
  });
});
