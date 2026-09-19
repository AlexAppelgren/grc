import { test } from './support/api-guard';

// billing: the @e2e scenarios from backend/apps/billing/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('billing journeys', () => {
  test.fixme("NFR-S17: A plan holds limits and a price as an integer minor unit", async () => {
    // pending: NFR-S17 (NFR-05)
  });

  test.fixme("NFR-S19: Usage is metered and visible to the tenant and the platform", async () => {
    // pending: NFR-S19 (NFR-05)
  });
});
