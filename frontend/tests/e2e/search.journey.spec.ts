import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// search: the @e2e scenarios from backend/apps/search/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

// The seed's Ask fixtures (backend/apps/shared/e2e_seed.py, EXPECTED_ASK), proved by the
// seed-integrity guard: the answered question retrieves the research payment duty, which
// the lead change (adopted, in force twenty days after the tenant-local today) is
// confirmed to move; the unsupported one retrieves nothing in the seeded library.
const ANSWERED_QUESTION = 'What are our obligations on research payments?';
const UNSUPPORTED_QUESTION = 'Do we need a licence for crypto custody?';
const RESEARCH = 'obl-research-payments';
const PENDING_OFFSET = 20;

/** The tenant-local today plus `offsetDays`, as a plain date the "As of" field takes. */
function tenantDay(offsetDays: number): Date {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const [year, month, day] = today.split('-').map(Number);
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, (day ?? 1) + offsetDays));
}

function isoDay(offsetDays: number): string {
  return tenantDay(offsetDays).toISOString().slice(0, 10);
}

/** As the screen's own `formatDate` renders a plain date: "D MMM YYYY", UTC. */
function dayText(offsetDays: number): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(tenantDay(offsetDays));
}

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

/** Ask the question from the Ask tab and wait for the answer to close, whichever it is. */
async function askQuestion(page: Page, question: string): Promise<void> {
  await page.getByRole('searchbox', { name: 'Question' }).fill(question);
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('[data-ask-answer="done"], [data-ask-answer="none"]').first()).toBeVisible();
}

/** Every statement of the closed answer carries at least one citation number, and each
 * number is a source the answer lists. */
async function expectEveryStatementCited(page: Page): Promise<void> {
  const answer = page.locator('[data-ask-answer="done"]');
  const statements = answer.locator('[data-ask-statement]');
  await expect(statements.first()).toBeVisible();
  const sources = answer.getByRole('list', { name: 'Sources' }).getByRole('listitem');
  const listed = new Set(await sources.evaluateAll((items) => items.map((item) => item.getAttribute('value'))));
  for (const marks of await statements.locator('sup').allTextContents()) {
    const numbers = marks.split(',').map((mark) => mark.trim());
    expect(numbers.length).toBeGreaterThan(0);
    for (const number of numbers) {
      expect(number).toMatch(/^\d+$/);
      expect(listed.has(number)).toBe(true);
    }
  }
}

/** The statement resting on the research payment duty carries its pending change as a warning. */
async function expectPendingChangeFlagged(page: Page): Promise<void> {
  const pill = page.locator('[data-ask-answer="done"] [data-ask-statement]').getByText(`Change pending: ${dayText(PENDING_OFFSET)}`, { exact: true });
  await expect(pill).toBeVisible();
  await expect(pill).toHaveAttribute('data-pill', 'warning');
}

/** A source opens the obligation it cites. */
async function openCitedObligation(page: Page): Promise<void> {
  const sources = page.locator('[data-ask-answer="done"]').getByRole('list', { name: 'Sources' });
  await sources.getByRole('link', { name: /^FFFS 2017:2, / }).first().click();
  await expect(page).toHaveURL(/\/inventory\/obligations\/[0-9a-f-]{36}$/);
  await expect(page.locator(`[data-obligation="${RESEARCH}"] [data-header-pills]`)).toBeVisible();
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

  test("SRC-S4: An answer cites every statement and flags pending changes", async ({ page, apiGuard }) => {
    // The AI log row the answer writes (purpose, model, input reference, output and
    // citations) is proved at the backend (apps/search/tests_scenarios.py::test_src_s4):
    // no screen shows it to a reader.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await page.goto('/search?mode=ask');
    await askQuestion(page, ANSWERED_QUESTION);

    // Labelled AI output, read as of today since no date was set.
    const answer = page.locator('[data-ask-answer="done"]');
    await expect(answer.getByText(`Answer drafted by AI from inventory records only, as of ${dayText(0)}`, { exact: true })).toBeVisible();
    await expectEveryStatementCited(page);
    await expectPendingChangeFlagged(page);

    // "Wrong", with the reader's reason, is logged with the answer.
    await answer.getByRole('button', { name: 'Wrong', exact: true }).click();
    await answer.getByLabel('What is wrong?').fill('The answer misses the exemption for minor non-monetary benefits.');
    await answer.getByRole('button', { name: 'Send', exact: true }).click();
    await expect(answer.getByRole('status').getByText('Thank you. Your feedback is logged with the answer.', { exact: true })).toBeVisible();

    await openCitedObligation(page);
  });

  test("SRC-S5: A question without support returns \"no answer\"", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await page.goto('/search?mode=ask');
    await askQuestion(page, UNSUPPORTED_QUESTION);

    // No answer, and nothing invented in its place: no statement, no source.
    const none = page.locator('[data-ask-answer="none"]');
    await expect(none.getByRole('heading', { name: 'No answer in the inventory' })).toBeVisible();
    await expect(page.locator('[data-ask-statement]')).toHaveCount(0);
    await expect(page.getByRole('list', { name: 'Sources' })).toHaveCount(0);

    // "Search instead" runs the same words as a plain search, and the question never
    // reaches the address bar.
    await none.getByRole('button', { name: 'Search instead' }).click();
    await expect(page).not.toHaveURL(/mode=ask/);
    await expect(page.getByRole('tab', { name: 'Search' })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('searchbox', { name: 'Search' })).toHaveValue(UNSUPPORTED_QUESTION);
    await expect(rows(page).first().or(page.getByRole('heading', { name: 'No match in the inventory' })).first()).toBeVisible();
    expect(page.url()).not.toContain('crypto');
  });

  test.fixme("SRC-S7: Saved searches notify and show what changed since the last visit", async () => {
    // pending: SRC-S7 (SRC-04, chunk 13)
  });

  test("SRC-S10 J-7 @smoke: search by identifier and by concept, then Ask with citations and \"as of\"", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);

    // The identifier hit is first, won by its words.
    await runSearch(page, 'FFFS 2017:2');
    await expect(rows(page).first()).toContainText('FFFS 2017:2');
    await expect(rows(page).first().getByText('Keyword match')).toBeVisible();

    // The concept hit is relevant, found by its meaning.
    await runSearch(page, 'nudging in onboarding');
    await expect(rows(page).first()).toContainText('Make appropriateness warnings prominent');
    await expect(rows(page).first().getByText('Concept match')).toBeVisible();

    // Ask, as of a day ahead of today and before the pending change takes effect.
    await page.getByRole('tab', { name: 'Ask a question' }).click();
    await expect(page).toHaveURL(/mode=ask/);
    const asOf = isoDay(10);
    await page.getByLabel('As of').fill(asOf);
    await expect(page).toHaveURL(new RegExp(`asOf=${asOf}`));
    await askQuestion(page, ANSWERED_QUESTION);

    const answer = page.locator('[data-ask-answer="done"]');
    await expect(answer.getByText(`Answer drafted by AI from inventory records only, as of ${dayText(10)}`, { exact: true })).toBeVisible();
    await expectEveryStatementCited(page);
    await expectPendingChangeFlagged(page);
    await openCitedObligation(page);
  });
});
