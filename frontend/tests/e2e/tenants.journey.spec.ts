import { test } from './support/api-guard';

// tenants: the @e2e scenarios from backend/apps/tenants/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('tenants journeys', () => {
  test.fixme("TEN-S1: A tenant profile holds timezone, languages and the onboarding checklist", async () => {
    // pending: TEN-S1 (TEN-01)
  });

  test.fixme("TEN-S2: Legal entities and products are scoped like obligations", async () => {
    // pending: TEN-S2 (TEN-02)
  });

  test.fixme("TEN-S4: An out-of-office delegate receives approvals and reminders", async () => {
    // pending: TEN-S4 (TEN-04)
  });

  test.fixme("TEN-S5: Removing a member with open work offers bulk reassignment", async () => {
    // pending: TEN-S5 (TEN-05)
  });

  test.fixme("TEN-S6: A support access grant is visible, time-boxed and logged", async () => {
    // pending: TEN-S6 (TEN-06)
  });

  test.fixme("TEN-S7 J-8 @smoke: tenant B cannot see tenant A", async () => {
    // pending: TEN-S7 (TEN-06, J-8)
  });

  test.fixme("ADM-S1: Tenant admin surfaces are gated by their own permissions", async () => {
    // pending: ADM-S1 (ADM-01, ADM-03)
  });

  test.fixme("ADM-S2: The members screen invites, assigns roles, re-issues enrolment and revokes sessions", async () => {
    // pending: ADM-S2 (ADM-01)
  });

  test.fixme("ADM-S3: User administration and business configuration can sit with different people", async () => {
    // pending: ADM-S3 (ADM-03)
  });
});
