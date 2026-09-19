import { test } from './support/api-guard';

// watch: the @e2e scenarios from backend/apps/watch/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('watch journeys', () => {
  test.fixme("WAT-S1: The source registry and coverage log show what was checked and with what result", async () => {
    // pending: WAT-S1 (WAT-01)
  });

  test.fixme("WAT-S2: One record per reform carries a timeline with partial dates", async () => {
    // pending: WAT-S2 (WAT-02)
  });

  test.fixme("WAT-S4: Types, flags and scope come from vocabularies and stay suggestions until confirmed", async () => {
    // pending: WAT-S4 (WAT-03)
  });

  test.fixme("WAT-S6: Links to affected obligations carry a confidence and are confirmed by a person", async () => {
    // pending: WAT-S6 (WAT-04)
  });

  test.fixme("WAT-S7: The \"So what?\" is AI-drafted until a person confirms or rewrites it per tenant", async () => {
    // pending: WAT-S7 (WAT-05)
  });

  test.fixme("WAT-S8: A tenant requests a source and private sources stay private", async () => {
    // pending: WAT-S8 (WAT-06)
  });

  test.fixme("WAT-S9: The change row renders its pills in the fixed slot order", async () => {
    // pending: WAT-S9 (WAT-03, NFR-03)
  });
});
