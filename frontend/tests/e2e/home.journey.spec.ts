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
