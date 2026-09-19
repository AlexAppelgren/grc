import { test } from './support/api-guard';

// home: the @e2e scenarios from backend/apps/home/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('home journeys', () => {
  test.fixme("HOM-S1: Today shows the next dates, the lead item, decisions, standing and source health", async () => {
    // pending: HOM-S1 (HOM-01)
  });

  test.fixme("HOM-S2: The same short list appears on a phone", async () => {
    // pending: HOM-S2 (HOM-01)
  });

  test.fixme("HOM-S3: The weekly briefing is reachable from home and snapshotted when emailed", async () => {
    // pending: HOM-S3 (HOM-02)
  });

  test.fixme("HOM-S4: The roadmap shows quarters with regulatory dates and our own deadlines", async () => {
    // pending: HOM-S4 (HOM-03)
  });

  test.fixme("HOM-S5: Upcoming changes are public facts and the calendar feed is revocable", async () => {
    // pending: HOM-S5 (HOM-04)
  });

  test.fixme("HOM-S6: A roadmap item's pill is the urgency or \"Our deadline\"", async () => {
    // pending: HOM-S6 (HOM-03)
  });
});

// PRD 0.3: My work (HOM-05, J-9) and a certificate's dates on the roadmap
// (HOM-03, TEN-02). Each stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('my work and certificate deadlines', () => {
  test.fixme("HOM-S7: My work lists what I'm responsible for or take part in, most urgent first", async () => {
    // pending: HOM-S7 (HOM-05, AC-HOM1)
  });

  test.fixme("HOM-S9: A department head sees the department's work, naming who is responsible", async () => {
    // pending: HOM-S9 (HOM-05, TEN-02, TEN-03)
  });

  test.fixme("HOM-S13: J-9: Monday morning", async () => {
    // pending: HOM-S13 (HOM-05, COL-04, TEN-03, J-9)
  });

  test.fixme("HOM-S15: A certificate's expiry and next audit are our deadlines, never in the calendar feed", async () => {
    // pending: HOM-S15 (HOM-03, HOM-04, TEN-02, AC-TEN1)
  });
});
