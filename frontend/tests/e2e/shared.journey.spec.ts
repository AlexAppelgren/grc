import { readFileSync } from 'node:fs';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS } from './support/passkeys';
import { CHUNK5_WATCH, openChangeByStableKey, openWatchFeed, signInAsSv } from './support/watch-coverage';

// shared: the @e2e scenarios from backend/apps/shared/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('shared journeys', () => {
  test.fixme("NFR-S7: Every screen reaches real data within its budget", async () => {
    // pending: NFR-S7 (NFR-02)
  });

  test.fixme("NFR-S8: The pill gallery matches the design card in both themes", async () => {
    // pending: NFR-S8 (NFR-03, AC-NFR3)
  });

  test.fixme("NFR-S9: Every text-on-surface pair passes WCAG AA in both themes", async () => {
    // pending: NFR-S9 (NFR-03, AC-NFR3)
  });

  // The catalog half of I18N-S3 runs before any journey: `npm run check:messages`
  // fails on a key missing in either language (scripts/messages-check.test.mjs),
  // and `npm run lint` on a string literal in JSX text (react/jsx-no-literals,
  // eslint.config.js). This is the person's half: the interface switched to
  // Swedish from the rail's account menu and back from the More sheet on a phone,
  // the vocabulary labels coming from their Swedish rows. The login is its own
  // (reserved for I18N-S3), because the language is saved on the person and every
  // session of theirs follows it.
  test('I18N-S3: Every UI string is in the catalog for every shipped language', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    const desktop = page.viewportSize();
    if (desktop === null) throw new Error('the journey needs a fixed viewport');
    // Waits for the shell in either language, so a retry after a run whose teardown
    // failed still signs in, fails on English below and restores it in the teardown.
    await signInAsSv(page, LOGINS.language);
    const who = page.locator('[data-who-panel]');
    // Named "…, account menu" in English and "…, kontomeny" in Swedish.
    const accountMenu = who.getByRole('button', { name: /^Nils Åberg, / });
    // Each language is named by its own row, in its own words, never by a catalog.
    const svenskaName = /^Svenska$/;
    const englishName = /^English$/;
    const svenska = page.getByRole('menuitemradio', { name: svenskaName });
    const english = page.getByRole('menuitemradio', { name: englishName });
    // The role and the urgency are vocabulary rows, seeded with a label per language.
    const change = page.locator(`[data-change="${CHUNK5_WATCH.timelineChange}"]`);
    const urgency = (label: RegExp) => change.locator('[data-pill]').filter({ hasText: label });
    try {
      await openWatchFeed(page);
      await expect(who).toContainText('Example Bank AB · Contributor');
      await expect(urgency(/^Within 3 months$/)).toBeVisible();

      await accountMenu.click();
      await expect(english).toHaveAttribute('aria-checked', 'true');
      await svenska.click();
      // The menu stays open and changes language with the rest of the page.
      await expect(svenska).toHaveAttribute('aria-checked', 'true');
      await expect(page.getByRole('group', { name: svCopy('common', 'language.label') })).toBeVisible();
      await page.keyboard.press('Escape');

      const main = page.getByRole('navigation', { name: svCopy('nav', 'nav.main') });
      await expect(main.getByRole('link', { name: svCopy('nav', 'nav.watch') })).toHaveAttribute('aria-current', 'page');
      await expect(who).toContainText('Example Bank AB · Bidragsgivare');
      await expect(urgency(/^Inom 3 månader$/)).toBeVisible();

      // Saved on the person, not the page: another screen, loaded from cold, reads Swedish too.
      await page.goto('/');
      await expect(page.getByRole('heading', { level: 1, name: svCopy('today', 'today.title') })).toBeVisible();

      // Back to English on a phone, where the account lives in the More sheet.
      await page.setViewportSize({ width: 375, height: 812 });
      await page
        .getByRole('navigation', { name: svCopy('nav', 'nav.main') })
        .getByRole('button', { name: svCopy('nav', 'nav.more') })
        .click();
      const svSheet = page.getByRole('dialog', { name: svCopy('nav', 'nav.more') }).getByRole('group', { name: svCopy('common', 'language.label') });
      await expect(svSheet.getByRole('radio', { name: svenskaName })).toBeChecked();
      // A click, not check(): the radio follows the saved language, so it turns only once the save lands.
      await svSheet.getByRole('radio', { name: englishName }).click();
      // The sheet stays open and changes language with the rest of the page.
      const enSheet = page.getByRole('dialog', { name: 'More' }).getByRole('group', { name: 'Language' });
      await expect(enSheet.getByRole('radio', { name: englishName })).toBeChecked();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
      await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();

      await page.setViewportSize(desktop);
      await expect(who).toContainText('Example Bank AB · Contributor');
    } finally {
      // Teardown that runs on failure too: the login goes back to English, from the
      // rail. A fresh load closes whatever was open; choosing the language in use saves nothing.
      await page.setViewportSize(desktop);
      await page.goto('/');
      await accountMenu.click();
      await english.click();
      await expect(english).toHaveAttribute('aria-checked', 'true');
      await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    }
  });

  // The browser runs in New York, so only the tenant's own timezone can put Stockholm
  // wall time on the screen: a moment formatted in the browser's local time fails.
  // That the tenant's zone beats the default one is format.test.ts's, because tenant A
  // and the default are both Europe/Stockholm.
  test.describe('in a browser in another timezone', () => {
    test.use({ timezoneId: 'America/New_York' });

    test('I18N-S4: Dates, numbers and partial dates format per language and timezone', async ({ page, apiGuard }) => {
      allowFreshContext(apiGuard);
      // The one seeded login whose own language is Swedish, in tenant A (Europe/Stockholm).
      await signInAsSv(page, LOGINS.readerSv);
      // The journeys run in one pinned language: the browser is English
      // (playwright.config.ts, `locale: 'en-GB'`) and every seeded login's own
      // language is `en` unless the roster says otherwise (e2e_logins.py). The
      // Swedish below is this person's own saved language, never the browser's.
      expect(await page.evaluate(() => navigator.language)).toBe('en-GB');

      // The dates are read from the change as the server sends it, so the journey
      // asserts how they render, never a date written into the test.
      const read = page.waitForResponse(async (response) => {
        if (response.request().method() !== 'GET' || !/^\/api\/v1\/changes\/[^/]+$/.test(new URL(response.url()).pathname)) return false;
        return ((await response.json()) as ChangeRead).stableKey === CHUNK5_WATCH.timelineChange;
      });
      await openChangeByStableKey(page, CHUNK5_WATCH.timelineChange);
      const change = (await (await read).json()) as ChangeRead;

      // A moment stored in UTC reads as Stockholm wall time, in Swedish ("23 sep. 2026 16:20").
      const fetched = change.documents.find((d) => d.fetchedAt !== null);
      if (fetched?.fetchedAt == null) throw new Error('the seeded change has no fetched document');
      const fetchedAt = fetched.fetchedAt;
      const stockholm = await page.evaluate(
        (iso) =>
          new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Stockholm', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(
            new Date(iso),
          ),
        fetchedAt,
      );
      const line = page.locator(`[data-document="${fetched.id}"]`);
      await expect(line).toContainText(stockholm);
      // Never the UTC clock the moment is stored in.
      await expect(line).not.toContainText(new Date(fetchedAt).toISOString().slice(11, 16));

      // An in-force date known only to its quarter reads as the Swedish quarter ("kv. 4 2026").
      const inForce = change.events.find((e) => e.datePrecision === 'quarter' && e.eventDate !== null);
      if (inForce?.eventDate == null) throw new Error('the seeded change has no quarter-precision date');
      const year = inForce.eventDate.slice(0, 4);
      const quarter = Math.ceil(Number(inForce.eventDate.slice(5, 7)) / 3);
      await expect(page.locator('[data-change-timeline]').getByText(`kv. ${quarter} ${year}`, { exact: true })).toBeVisible();
    });
  });
});

/** What I18N-S4 reads of a change: its pages and its timeline, as `GET /changes/{id}` sends them. */
interface ChangeRead {
  stableKey: string;
  documents: { id: string; fetchedAt: string | null }[];
  events: { eventDate: string | null; datePrecision: string | null }[];
}

/** Swedish copy, read from the catalog the app itself loads, so a reworded string never breaks the journey. */
function svCopy(namespace: string, key: string): string {
  const catalog = JSON.parse(readFileSync(new URL(`../../src/messages/${namespace}/sv.json`, import.meta.url), 'utf8')) as Record<string, string>;
  const value = catalog[key];
  if (value === undefined) throw new Error(`the sv catalog of ${namespace} has no "${key}"`);
  return value;
}
