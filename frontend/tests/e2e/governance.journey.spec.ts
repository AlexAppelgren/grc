import { test } from './support/api-guard';

// governance: the @e2e scenarios from backend/apps/governance/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('governance journeys', () => {
  test.fixme("AUD-S3: The audit log screen shows who did what, with before and after", async () => {
    // pending: AUD-S3 (AUD-01)
  });

  test.fixme("AUD-S4: Every model output is logged with its review state", async () => {
    // pending: AUD-S4 (AUD-02)
  });

  test.fixme("AUD-S5: A problem report is resolved by a proposal", async () => {
    // pending: AUD-S5 (AUD-03)
  });

  test.fixme("ADM-S4: The platform console offers each surface to the platform role that owns it", async () => {
    // pending: ADM-S4 (ADM-02)
  });

  test.fixme("ADM-S5: System health names what is wrong", async () => {
    // pending: ADM-S5 (ADM-02)
  });

  test.fixme("ADM-S6: Tenants, plans and support access are managed from the console", async () => {
    // pending: ADM-S6 (ADM-02)
  });
});
