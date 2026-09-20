import { test } from './support/api-guard';

// agents: the @e2e scenarios from backend/apps/agents/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('agents journeys', () => {
  test.fixme("AGT-S4: Agent definitions are versioned and owned by the platform", async () => {
    // pending: AGT-S4 (AGT-03)
  });

  test.fixme("AGT-S5: A tenant controls its agents without touching their instructions", async () => {
    // pending: AGT-S5 (AGT-04)
  });

  test.fixme("AGT-S13: A bank cannot switch off, pause or re-scope one of bleqq's agents", async () => {
    // pending: AGT-S13 (AGT-03, AGT-04)
  });

  test.fixme("AGT-S6: The budget cap pauses runs and the AI off switch stops every model call", async () => {
    // pending: AGT-S6 (AGT-04)
  });

  test.fixme("AGT-S7: Research requests ask an agent to check, research or re-tag", async () => {
    // pending: AGT-S7 (AGT-05)
  });

  test.fixme("AGT-S10 J-4 @smoke: an agent registers a change and a proposal, an editor approves, the tenant sees what changed", async () => {
    // pending: AGT-S10 (AGT-01, WAT-02, PRO-02, INV-04, J-4)
  });
});
