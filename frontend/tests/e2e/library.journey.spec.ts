import { test } from './support/api-guard';

// library: the @e2e scenarios from backend/apps/library/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('library journeys', () => {
  test.fixme("INV-S1: An instrument carries its identity, dates and lineage", async () => {
    // pending: INV-S1 (INV-01)
  });

  test.fixme("INV-S2: The provision tree holds verbatim text versions", async () => {
    // pending: INV-S2 (INV-02)
  });

  test.fixme("INV-S3: An obligation states the duty and its facets", async () => {
    // pending: INV-S3 (INV-03)
  });

  test.fixme("INV-S4: \"As of\" returns the version in force on a date", async () => {
    // pending: INV-S4 (INV-04, AC-INV1)
  });

  test.fixme("INV-S5: The diff between two versions is at sentence level", async () => {
    // pending: INV-S5 (INV-04, AC-INV1)
  });

  test.fixme("INV-S6: Text exists in the original language with labelled translations", async () => {
    // pending: INV-S6 (INV-05)
  });

  test.fixme("INV-S7: Every record has a source link, a last-verified date and a way to report it", async () => {
    // pending: INV-S7 (INV-06)
  });
});
