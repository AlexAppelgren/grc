import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// search: the @e2e scenarios from backend/apps/search/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

function rows(page: Page) {
  return page.locator('[data-search-rows] > *');
}

async function runSearch(page: Page, query: string): Promise<void> {
  await page.goto('/search');
  await page.getByRole('searchbox', { name: 'Search' }).fill(query);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  // Settle before reading a row: either a result or the no-match state.
  await expect(rows(page).first().or(page.getByRole('heading', { name: 'No match in the inventory' })).first()).toBeVisible();
}

test.describe('search journeys', () => {
  test("SRC-S1: An identifier is won by keyword and a concept by vector in one query", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);

    // An identifier: FFFS 2017:2's own obligations come back matched by
    // their words, and the instrument's own name is the first pill.
    await runSearch(page, 'FFFS 2017:2');
    const first = rows(page).first();
    await expect(first).toContainText('FFFS 2017:2');
    await expect(first.getByText('Keyword match')).toBeVisible();

    // A concept: none of these words is in the ESMA warnings obligation's
    // own text, and it still comes back, matched by its meaning.
    await runSearch(page, 'nudging in onboarding');
    const concept = rows(page).first();
    await expect(concept).toContainText('Make appropriateness warnings prominent');
    await expect(concept.getByText('Concept match')).toBeVisible();
  });

  test("SRC-S3: Filters come from vocabularies, \"as of\" picks the version, and each hit states its match kind", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);

    // Each filter is read back from the URL before the next one is set: the
    // filter row is controlled by the URL, and a second change fired before
    // the first one lands would otherwise overwrite it.
    await page.goto('/search');
    await page.getByRole('combobox', { name: 'Jurisdiction' }).selectOption('se');
    await expect(page).toHaveURL(/jurisdiction=se/);
    await page.getByRole('combobox', { name: 'Duty type' }).selectOption('reporting');
    await expect(page).toHaveURL(/dutyType=reporting/);
    await page.getByLabel('As of').fill('2026-09-16');
    await expect(page).toHaveURL(/asOf=2026-09-16/);
    await page.getByRole('searchbox', { name: 'Search' }).fill('report');
    await page.getByRole('button', { name: 'Search', exact: true }).click();

    // Only the one record carrying both keys comes back, and it states how
    // it matched; a renamed vocabulary label could never change this, since
    // what travelled was the key.
    await expect(rows(page)).toHaveCount(1);
    const hit = rows(page).first();
    await expect(hit).toContainText('Report ISK standard income to Skatteverket every year');
    await expect(hit.getByText(/^(Keyword match|Concept match|Keyword and concept)$/)).toBeVisible();
  });

  test.fixme("SRC-S4: An answer cites every statement and flags pending changes", async () => {
    // pending: SRC-S4 (SRC-03, AC-SRC2)
  });

  test.fixme("SRC-S5: A question without support returns \"no answer\"", async () => {
    // pending: SRC-S5 (SRC-03, AC-SRC2)
  });

  test.fixme("SRC-S7: Saved searches notify and show what changed since the last visit", async () => {
    // pending: SRC-S7 (SRC-04, chunk 13)
  });

  test.fixme("SRC-S10 J-7 @smoke: search by identifier and by concept, then Ask with citations and \"as of\"", async () => {
    // pending: SRC-S10 (SRC-01, SRC-02, SRC-03, AC-SRC1, AC-SRC2, J-7)
  });
});
