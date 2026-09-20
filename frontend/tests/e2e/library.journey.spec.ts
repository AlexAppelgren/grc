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

// PRD 0.3: a standard is an instrument of public facts with no provision tree
// (INV-08). It stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('standards in the library', () => {
  test.fixme("INV-S11: An edition of a standard is an instrument with public facts and no text", async () => {
    // pending: INV-S11 (INV-01, INV-02, INV-08)
  });
});

// PRD 0.4: a library record confirmed by agents is labelled machine-confirmed
// (INV-05, D-62). It stays test.fixme until the task in
// docs/plans/briefs/CHUNK4_TASKS.md that builds it lands.
test.describe('machine-confirmed provenance', () => {
  test.fixme("INV-S14: A record an agent confirmed reads as machine-confirmed", async () => {
    // pending: INV-S14 (INV-05, INV-06, PRO-02)
  });
});
