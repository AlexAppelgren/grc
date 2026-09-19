import { test } from './support/api-guard';

// register: the @e2e scenarios from backend/apps/register/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('register journeys', () => {
  test.fixme("REG-S1: Applicability changes through a request a second person approves", async () => {
    // pending: REG-S1 (REG-01)
  });

  test.fixme("REG-S3: Compliance status and its details are kept per legal entity", async () => {
    // pending: REG-S3 (REG-02)
  });

  test.fixme("REG-S5: A gap has an owner, severity, target date and remediation", async () => {
    // pending: REG-S5 (REG-03)
  });

  test.fixme("REG-S6: Risk acceptance is behind four eyes with step-up", async () => {
    // pending: REG-S6 (REG-03)
  });

  test.fixme("REG-S7: Assessment history and \"How we read this rule\" are kept per obligation", async () => {
    // pending: REG-S7 (REG-04)
  });

  test.fixme("REG-S8: Linked internal items carry external references", async () => {
    // pending: REG-S8 (REG-05)
  });

  test.fixme("REG-S9: Yearly attestation and waivers", async () => {
    // pending: REG-S9 (REG-06)
  });
});
