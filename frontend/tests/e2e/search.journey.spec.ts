import { test } from './support/api-guard';

// search: the @e2e scenarios from backend/apps/search/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('search journeys', () => {
  test.fixme("SRC-S1: An identifier is won by keyword and a concept by vector in one query", async () => {
    // pending: SRC-S1 (SRC-01, AC-SRC1)
  });

  test.fixme("SRC-S3: Filters come from vocabularies, \"as of\" picks the version, and each hit states its match kind", async () => {
    // pending: SRC-S3 (SRC-02)
  });

  test.fixme("SRC-S4: An answer cites every statement and flags pending changes", async () => {
    // pending: SRC-S4 (SRC-03, AC-SRC2)
  });

  test.fixme("SRC-S5: A question without support returns \"no answer\"", async () => {
    // pending: SRC-S5 (SRC-03, AC-SRC2)
  });

  test.fixme("SRC-S7: Saved searches notify and show what changed since the last visit", async () => {
    // pending: SRC-S7 (SRC-04)
  });

  test.fixme("SRC-S10 J-7 @smoke: search by identifier and by concept, then Ask with citations and \"as of\"", async () => {
    // pending: SRC-S10 (SRC-01, SRC-02, SRC-03, AC-SRC1, AC-SRC2, J-7)
  });
});
