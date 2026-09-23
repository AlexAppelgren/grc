import { test } from './support/api-guard';

// shared: the @e2e scenarios from backend/apps/shared/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// NFR-S8, the pill gallery, is real in pills.gallery.spec.ts, beside the
// screenshot baselines it compares against.

test.describe('shared journeys', () => {
  test.fixme("NFR-S7: Every screen reaches real data within its budget", async () => {
    // pending: NFR-S7 (NFR-02)
  });

  test.fixme("NFR-S9: Every text-on-surface pair passes WCAG AA in both themes", async () => {
    // pending: NFR-S9 (NFR-03, AC-NFR3)
  });

  test.fixme("I18N-S3: Every UI string is in the catalog for every shipped language", async () => {
    // pending: I18N-S3 (I18N-02)
  });

  test.fixme("I18N-S4: Dates, numbers and partial dates format per language and timezone", async () => {
    // pending: I18N-S4 (I18N-02)
  });
});
