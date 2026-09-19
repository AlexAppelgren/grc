import { test } from './support/api-guard';

// taxonomy: the @e2e scenarios from backend/apps/taxonomy/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('taxonomy journeys', () => {
  test.fixme("VOC-S2: An admin adds a change type, a tag and a sub-status without a deploy", async () => {
    // pending: VOC-S2 (VOC-01, AC-VOC1)
  });

  test.fixme("VOC-S3: The vocabulary screen renders the real pill with usage count, rename and reorder", async () => {
    // pending: VOC-S3 (VOC-02)
  });

  test.fixme("VOC-S4: Retiring a used value keeps history readable and leaves pickers", async () => {
    // pending: VOC-S4 (VOC-02, AC-VOC2)
  });

  test.fixme("VOC-S5: Merging re-points duplicates in one audited transaction", async () => {
    // pending: VOC-S5 (VOC-02)
  });

  test.fixme("VOC-S6: Create where you use it offers Create or Suggest by permission", async () => {
    // pending: VOC-S6 (VOC-03)
  });

  test.fixme("VOC-S7: A near-duplicate is refused with the near match offered", async () => {
    // pending: VOC-S7 (VOC-03, AC-VOC3)
  });

  test.fixme("VOC-S11: A library vocabulary change goes through the proposal queue", async () => {
    // pending: VOC-S11 (VOC-07)
  });

  test.fixme("VOC-S12: Bulk tagging from a list previews and writes one audit entry", async () => {
    // pending: VOC-S12 (VOC-08)
  });

  test.fixme("VOC-S15 J-5 @smoke: a flag is added, used, rendered as brand, renamed and merged", async () => {
    // pending: VOC-S15 (VOC-01, VOC-02, VOC-07, AC-VOC1, AC-VOC2, J-5)
  });

  test.fixme("FP-S2: A footprint change previews, waits for a second person and audits per term", async () => {
    // pending: FP-S2 (FP-02, AC-FP1)
  });

  test.fixme("FP-S4: Every surface respects the footprint and offers a way to look outside it", async () => {
    // pending: FP-S4 (FP-03)
  });

  test.fixme("FP-S5 J-6 @smoke: footprint change with preview and second-person approval", async () => {
    // pending: FP-S5 (FP-01, FP-02, FP-03, AC-FP1, J-6)
  });
});
