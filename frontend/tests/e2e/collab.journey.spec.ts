import { test } from './support/api-guard';

// collab: the @e2e scenarios from backend/apps/collab/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('collab journeys', () => {
  test.fixme("COL-S1: A comment with a mention notifies the mentioned person", async () => {
    // pending: COL-S1 (COL-01)
  });

  test.fixme("COL-S2: Reminders, escalation and the digest reach people in their language", async () => {
    // pending: COL-S2 (COL-02)
  });

  test.fixme("COL-S4: A user follows a record and hears about changes", async () => {
    // pending: COL-S4 (COL-03)
  });
});
