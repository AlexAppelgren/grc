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

// PRD 0.3: participants on register entries and cases (COL-04) and the
// comments and mentions panel on My work (COL-01, HOM-05). Each stays
// test.fixme until the task in docs/plans/briefs/FEATURES_0_3_TASKS.md lands.
test.describe('participants, comments and mentions', () => {
  test.fixme("COL-S6: A person or a team is added to a register entry, audited, and gains no access", async () => {
    // pending: COL-S6 (COL-04, AC-COL1)
  });

  test.fixme("COL-S7: A participant leaves a register entry on their own", async () => {
    // pending: COL-S7 (COL-04)
  });

  test.fixme("COL-S9: Case participants are managed by those who contribute, and refused across tenants", async () => {
    // pending: COL-S9 (COL-04, AC-COL1, NFR-01)
  });

  test.fixme("COL-S12: My comments and mentions are found on My work, limited to what I can read, and never logged", async () => {
    // pending: COL-S12 (COL-01, HOM-05)
  });
});
