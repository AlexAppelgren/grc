import { test } from './support/api-guard';

// reports: the @e2e scenarios from backend/apps/reports/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('reports journeys', () => {
  test.fixme("REP-S1: The dashboard shows the officer's figures from keys and categories", async () => {
    // pending: REP-S1 (REP-01)
  });

  test.fixme("REP-S2: The committee pack and the exports are produced by jobs", async () => {
    // pending: REP-S2 (REP-02)
  });

  test.fixme("REP-S4: A spreadsheet register imports with a dry run and a mapping asked once per value", async () => {
    // pending: REP-S4 (REP-03)
  });

  test.fixme("REP-S5: A tenant can leave with everything and have deletion verified", async () => {
    // pending: REP-S5 (REP-04)
  });
});
