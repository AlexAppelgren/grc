import { test } from './support/api-guard';

// integrations: the @e2e scenarios from backend/apps/integrations/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('integrations journeys', () => {
  test.fixme("INT-S1: A signed webhook is delivered from the outbox with a delivery log", async () => {
    // pending: INT-S1 (INT-01)
  });

  test.fixme("INT-S3: Actions export as tickets", async () => {
    // pending: INT-S3 (INT-02)
  });

  test.fixme("INT-S4: Audit events stream to the customer's SIEM", async () => {
    // pending: INT-S4 (INT-03)
  });
});
