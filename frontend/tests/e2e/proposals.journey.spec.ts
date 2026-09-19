import { test } from './support/api-guard';

// proposals: the @e2e scenarios from backend/apps/proposals/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('proposals journeys', () => {
  test.fixme("PRO-S3: Approval applies payload, version, audit row and re-index in one transaction", async () => {
    // pending: PRO-S3 (PRO-02)
  });

  test.fixme("PRO-S4: The reviewer corrects scope and wording before approving", async () => {
    // pending: PRO-S4 (PRO-02)
  });

  test.fixme("PRO-S5: Approving your own proposal answers four_eyes_violation", async () => {
    // pending: PRO-S5 (PRO-02, AC-PRO2)
  });

  test.fixme("PRO-S7: The queue is in the console and tenants see updates and report problems", async () => {
    // pending: PRO-S7 (PRO-03)
  });

  test.fixme("PRO-S8: A batch proposal previews and is approved whole or row by row", async () => {
    // pending: PRO-S8 (PRO-04)
  });

  test.fixme("PRO-S9: A rejection needs a reason and is audited", async () => {
    // pending: PRO-S9 (PRO-01)
  });
});
