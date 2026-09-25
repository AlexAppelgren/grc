import { test } from './support/api-guard';

// register: the @e2e scenarios from backend/apps/register/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('register journeys', () => {
  test.fixme("REG-S1: One compliance person sets applicability after confirming it", async () => {
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

// PRD 0.3: a legal entity follows a standard and lists its units (REG-01,
// REG-08, J-10). Each stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('standards per legal entity', () => {
  test.fixme("REG-S12: A legal entity follows a standard when its applicability is set to \"Applies\"", async () => {
    // pending: REG-S12 (REG-01, REG-02)
  });

  test.fixme("REG-S13: A tenant lists its clauses and controls as units in its own words", async () => {
    // pending: REG-S13 (REG-08)
  });

  test.fixme("REG-S14: Unit decisions are set from the paste in one confirmed call", async () => {
    // pending: REG-S14 (REG-01, REG-08, AC-REG1)
  });

  test.fixme("REG-S15: The register filtered by standard and entity is the Statement of Applicability", async () => {
    // pending: REG-S15 (REG-08)
  });

  test.fixme("REG-S16 J-10 @smoke: a legal entity follows a standard from regulatory scope to Statement of Applicability", async () => {
    // pending: REG-S16 (FP-02, TEN-02, REG-01, REG-08, J-10)
  });
});
