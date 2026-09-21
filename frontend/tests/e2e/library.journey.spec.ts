import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// library: the @e2e scenarios from backend/apps/library/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// The seed's anchor date. Every read here pins it, so nothing depends on today
// and the research payment version that takes effect on 2026-10-01 never
// changes what a step reads.
const AS_OF = '2026-09-16';

// Library titles are rows, not catalog copy, so a record is found by its
// stable key and never by a quoted literal.
const RESEARCH = 'obl-research-payments';
const DORA = 'obl-dora-ict-register';
const ESMA = 'obl-esma-warnings';

async function openInventory(page: Page): Promise<void> {
  await page.goto(`/inventory?asOf=${AS_OF}`);
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

/** From the inventory to one card, by stable key: the row's link carries the id. */
async function openObligation(page: Page, stableKey: string): Promise<void> {
  await openInventory(page);
  await page.locator(`[data-obligation="${stableKey}"]`).click();
  await expect(page.locator(`[data-obligation="${stableKey}"] [data-header-pills]`)).toBeVisible();
}

function headerPills(page: Page) {
  return page.locator('[data-header-pills] [data-pill]');
}

test.describe('library journeys', () => {
  test.fixme("INV-S1: An instrument carries its identity, dates and lineage", async () => {
    // pending: INV-S1 (INV-01)
  });

  test.fixme("INV-S2: The provision tree holds verbatim text versions", async () => {
    // pending: INV-S2 (INV-02)
  });

  test("INV-S3: An obligation states the duty and its facets", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);

    // The header slots in their order: instrument brand, regime information,
    // binding level information. A tone is chosen by the slot, never by a person.
    await openObligation(page, RESEARCH);
    await expect(headerPills(page)).toHaveText(['FFFS 2017:2', 'Securities', 'Binding']);
    await expect(headerPills(page).nth(0)).toHaveAttribute('data-pill', 'brand');
    await expect(headerPills(page).nth(1)).toHaveAttribute('data-pill', 'information');
    await expect(headerPills(page).nth(2)).toHaveAttribute('data-pill', 'information');

    // The duty and its facets: the type, the trigger, what is kept and what it costs.
    const duty = page.locator('[data-duty-panel]');
    await expect(duty.getByText('Type')).toBeVisible();
    await expect(duty.getByText('Record retention')).toBeVisible();
    await expect(page.locator('[data-scope-panel] [data-pill]').first()).toHaveAttribute('data-pill', 'brand');
    // Being on this card is not the judgement that the duty reaches this bank.
    await expect(page.locator('[data-pending-panel="register"]')).toBeVisible();

    // Every service selected reads "All services"; an empty list is no
    // restriction and says so in words, never as an empty row.
    await openObligation(page, DORA);
    await expect(page.locator('[data-scope-panel]').getByText('All services')).toBeVisible();
    await expect(page.locator('[data-scope-panel]').getByText('Not client-specific')).toBeVisible();

    // Guidance a bank complies with or explains, in the binding slot.
    await openObligation(page, ESMA);
    await expect(headerPills(page).getByText('Guidance, comply or explain')).toBeVisible();
    await expect(headerPills(page).getByText('Guidance, comply or explain')).toHaveAttribute('data-pill', 'warning');
  });

  test.fixme("INV-S4: \"As of\" returns the version in force on a date", async () => {
    // pending: INV-S4 (INV-04, AC-INV1)
  });

  test.fixme("INV-S5: The diff between two versions is at sentence level", async () => {
    // pending: INV-S5 (INV-04, AC-INV1)
  });

  test("INV-S6: Text exists in the original language with labelled translations", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    // The officer reads in English; the research payment summary is written in
    // Swedish, so what they are served is a machine translation and says so.
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, RESEARCH);

    const text = page.locator('[data-legal-text]');
    await expect(text.locator('[data-machine-translation]')).toHaveText('Machine translation from Swedish. The original is authoritative.');
    await expect(text.locator('[lang="en"]')).toBeVisible();

    // "Show original": the Swedish text, with no label of its own.
    await page.locator('[data-language-chips]').getByRole('button', { name: 'Swedish, original' }).click();
    await expect(text.locator('[lang="sv"]')).toBeVisible();
    await expect(text.locator('[data-machine-translation]')).toHaveCount(0);
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
