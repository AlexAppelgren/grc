import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// library: the @e2e scenarios from backend/apps/library/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// The seed's anchor date, which the inventory list is read as of. The cards
// themselves open on today's date, so a step on a card either chooses a
// version by its own chip, types the date it reads as of, or asserts only
// what reads the same on both sides of 2026-10-01, the day the research
// payment rules change: a run after that day must pass unchanged.
const AS_OF = '2026-09-16';

// The day the research payment rules change. The provision tree opens on the
// version in force today where the seeded bank is (Europe/Stockholm), so a
// journey works out which version that is from the same tenant-local date
// rather than assuming one.
const AMENDMENT_DAY = '2026-10-01';

function tenantToday(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

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

/** The Instruments tab, then one card by stable key: the row's link carries the id. */
async function openInstrument(page: Page, stableKey: string): Promise<void> {
  await page.goto('/inventory?tab=instruments');
  await expect(page.locator('[data-instrument-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  await page.locator(`[data-instrument="${stableKey}"]`).click();
  await expect(page.locator(`[data-instrument="${stableKey}"] [data-header-pills]`)).toBeVisible();
}

function headerPills(page: Page) {
  return page.locator('[data-header-pills] [data-pill]');
}

test.describe('library journeys', () => {
  test("INV-S1: An instrument carries its identity, dates and lineage", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openInstrument(page, 'fffs-2017-2');

    // The short name and jurisdiction are brand, the level and binding force
    // information: a tone is chosen by slot or kind, never by a person.
    await expect(headerPills(page)).toHaveText(['FFFS 2017:2', 'Supervisory regulation', 'Binding', 'Sweden', 'Securities']);
    await expect(headerPills(page).nth(0)).toHaveAttribute('data-pill', 'brand');
    await expect(headerPills(page).nth(1)).toHaveAttribute('data-pill', 'information');
    await expect(headerPills(page).nth(2)).toHaveAttribute('data-pill', 'information');
    await expect(headerPills(page).nth(3)).toHaveAttribute('data-pill', 'brand');

    // Identity: official reference, ELI where available (FFFS has none), the
    // authority and the in-force date with its day precision.
    const identity = page.locator('[data-identity-panel]');
    await expect(identity.getByText('FFFS 2017:2')).toBeVisible();
    await expect(identity.getByText('Not available')).toBeVisible();
    // The authority, a library fact rather than app copy (playbook's copy-drift check
    // only scans getByText for app copy, so a data value asserts through a locator).
    await expect(identity).toContainText('Finansinspektionen');
    await expect(identity.getByText('In force from 3 Jan 2018')).toBeVisible();

    // Lineage, grouped by relation and direction: FFFS 2026:11 amends this
    // instrument, and this instrument implements the delegated directive
    // (INV-01, T13's seeded amendment). Both are library facts, so they are
    // found through the group's key rather than quoted copy.
    await expect(page.locator('[data-lineage-group="amends:incoming"] [data-lineage-instrument="fffs-2026-11"]')).toBeVisible();
    await expect(page.locator('[data-lineage-group="implements:outgoing"] [data-lineage-instrument="celex-32017l0593"]')).toBeVisible();

    // The obligations from this instrument read inside our scope first, the
    // same list the inventory answers when filtered by it (FP-03, FP-04), with
    // the scope as one filter of three values, the total and a way into that list.
    const obligations = page.locator('[data-obligations-panel]');
    const scope = obligations.getByRole('group', { name: 'Scope' });
    await expect(scope.getByRole('button', { name: 'In our scope' })).toHaveAttribute('aria-pressed', 'true');
    await expect(scope.getByRole('button', { name: 'Markets we watch' })).toHaveAttribute('aria-pressed', 'false');
    await expect(scope.getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'false');
    await expect(obligations.locator(`[data-obligation="${RESEARCH}"]`)).toBeVisible();
    await expect(obligations.locator('[data-obligations-total]')).toHaveText(/^\d+ obligations?$/);
    const inventory = obligations.getByRole('link', { name: 'Open in the inventory' });
    await expect(inventory).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2');

    // The inventory it opens is filtered by this instrument, and its picker
    // says so rather than "All instruments".
    await inventory.click();
    await expect(page.locator(`[data-obligation-rows] [data-obligation="${RESEARCH}"]`)).toBeVisible();
    await expect(page.locator('[data-inventory-filters]').getByLabel('Instrument', { exact: true })).toHaveValue('fffs-2017-2');
  });

  test("INV-S2: The provision tree holds verbatim text versions", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openInstrument(page, 'fffs-2017-2');

    // 9 kap. 6 § carries a chip for each version, and opens on the current
    // text: the version in force today where the bank is, which changes on
    // 1 October 2026 when the amendment takes effect. The journey works out
    // which chip that is from the same date, then chooses each version by its
    // own chip.
    const section = page.locator('[data-provision="fffs-2017-2/9-6"]');
    await expect(section).toBeVisible();
    const before = section.getByRole('button', { name: 'In force 3 Jan 2018 to 30 Sept 2026' });
    const amended = section.getByRole('button', { name: 'In force from 1 Oct 2026' });
    const amendedToday = tenantToday() >= AMENDMENT_DAY;
    await expect(before).toHaveAttribute('aria-pressed', String(!amendedToday));
    await expect(amended).toHaveAttribute('aria-pressed', String(amendedToday));

    await before.click();
    await expect(before).toHaveAttribute('aria-pressed', 'true');
    await expect(amended).toHaveAttribute('aria-pressed', 'false');

    await amended.click();
    await expect(amended).toHaveAttribute('aria-pressed', 'true');
    // The transitional note is the fixture's own text (T8), not app copy.
    await expect(section).toContainText('The annual assessment is first due for research received after 1 October 2026.');

    // "Show what changed" opens the sentence-level diff between the two
    // versions, names both of them, and, because the officer reads an English
    // translation of Swedish law, says it is a machine translation.
    await section.getByRole('button', { name: 'Show what changed' }).click();
    const banner = section.locator('[data-diff-banner]');
    await expect(banner).toContainText('in force from 3 Jan 2018');
    await expect(banner).toContainText('in force from 1 Oct 2026');
    await expect(section.locator('[data-diff-banner] + [data-machine-translation]')).toHaveText('Machine translation. The original is authoritative.');
    await expect(section.locator('[data-legal-text] ins, [data-legal-text] del').first()).toBeVisible();

    // The provision half of INV-S7: with 6 § expanded, the card still shows
    // the instrument's own source link and verified date (chunk3-rest-T17).
    await expect(page.getByRole('link', { name: 'Source' })).toHaveAttribute('href', /^https?:\/\//);
    await expect(page.locator('[data-identity-panel]').getByText('Last verified')).toBeVisible();
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

  test("INV-S4: \"As of\" returns the version in force on a date", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, RESEARCH);

    // Both dates are typed, never taken from today: version 2 of this duty
    // takes effect on 1 October 2026, so a run either side of it would
    // otherwise read a different card.
    const asOf = page.getByLabel('As of');
    await asOf.fill('2026-06-30');
    await expect(page.locator('[data-as-of="2026-06-30"]')).toBeVisible();
    await expect(page.getByText('Showing version 1, in force on 30 Jun 2026.')).toBeVisible();
    await expect(page.locator('[data-version-bar]').getByRole('button', { name: 'Version 1' })).toHaveAttribute('aria-pressed', 'true');

    await asOf.fill('2026-10-01');
    await expect(page.locator('[data-as-of="2026-10-01"]')).toBeVisible();
    await expect(page.getByText('Showing version 2, in force on 1 Oct 2026.')).toBeVisible();
    await expect(page.locator('[data-version-bar]').getByRole('button', { name: 'Version 2, from 1 Oct 2026' })).toHaveAttribute('aria-pressed', 'true');

    // Back to today, and the address stays the record's own.
    await page.getByRole('button', { name: 'Back to today' }).click();
    await expect(page.locator('[data-as-of]')).toHaveCount(0);
  });

  test("INV-S5: The diff between two versions is at sentence level", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, RESEARCH);

    await page.getByRole('button', { name: 'Show what changed' }).click();
    const banner = page.locator('[data-diff-banner]');
    // Both effective dates are named: version 1 has been in force since the
    // record began, version 2 takes effect on 1 October 2026.
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('in force since it began');
    await expect(banner).toContainText('in force from 1 Oct 2026');

    // Sentence level: the sentences version 2 adds are marked, the ones that
    // stand are not, and a reader hears where the addition starts and ends.
    const text = page.locator('[data-legal-text]');
    await expect(text.locator('ins')).toHaveCount(2);
    await expect(text.locator('ins').first()).toContainText('annual assessment');
    await expect(text.locator('ins').first().getByText('Added text:')).toBeAttached();

    await page.getByRole('button', { name: 'Show what changed' }).click();
    await expect(banner).toHaveCount(0);
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

  test("INV-S7: Every record has a source link, a last-verified date and a way to report it", async ({ page, apiGuard }) => {
    // The provision half arrives with the provision tree panel (chunk3-rest-T18).
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, RESEARCH);

    // The public page the record was taken from, and when somebody last held
    // it against that page. The seed leaves no verifier, so no name is claimed.
    const provenance = page.locator('[data-provenance-panel]');
    await expect(provenance.getByText('Source')).toBeVisible();
    await expect(provenance.locator('[data-source-link]')).toHaveAttribute('href', /^https?:\/\//);
    await expect(provenance.getByText('Last verified')).toBeVisible();
    await expect(provenance.locator('[data-last-verified]')).toHaveText(/\d{4}$/);

    // "This looks wrong": the reader's own words, filed inside their own bank.
    await provenance.getByRole('button', { name: 'This looks wrong' }).click();
    const dialog = page.getByRole('dialog', { name: 'What looks wrong?' });
    await expect(dialog.getByText('Colleagues in your organisation read this and take it up. It reaches nobody outside your organisation.')).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Send report' })).toBeDisabled();
    await dialog.getByLabel('What you see').fill('The English summary says annually; the Swedish original says at least annually.');
    await dialog.getByRole('button', { name: 'Send report' }).click();
    await expect(dialog.getByText('Report sent. Thank you.')).toBeVisible();
    await dialog.getByRole('button', { name: 'Done' }).click();
    await expect(dialog).toBeHidden();

    // The instrument half: the same source link, verified date and report,
    // this time on FFFS 2017:2's own card (chunk3-rest-T17).
    await openInstrument(page, 'fffs-2017-2');
    const identity = page.locator('[data-identity-panel]');
    await expect(page.getByRole('link', { name: 'Source' })).toHaveAttribute('href', /^https?:\/\//);
    await expect(identity.getByText('Last verified')).toBeVisible();
    await expect(identity.locator('[data-last-verified]')).toHaveText(/\d{4}$/);

    await identity.getByRole('button', { name: 'This looks wrong' }).click();
    const instrumentDialog = page.getByRole('dialog', { name: 'What looks wrong?' });
    await instrumentDialog.getByLabel('What you see').fill('The in-force date does not match the source.');
    await instrumentDialog.getByRole('button', { name: 'Send report' }).click();
    await expect(instrumentDialog.getByText('Report sent. Thank you.')).toBeVisible();
    await instrumentDialog.getByRole('button', { name: 'Done' }).click();
    await expect(instrumentDialog).toBeHidden();
  });
});

// PRD 0.3: a standard is an instrument of public facts with no provision tree
// (INV-08). The one standard is seeded for E2E only (backend/apps/shared/e2e_seed.py,
// E2E_STANDARD_INSTRUMENT and E2E_STANDARD_OBLIGATION) and no seeded bank follows it,
// so its conformance duty is reached through "Show outside our scope". Its instrument
// carries only its regime, which tenant A holds, so the Instruments tab lists it.
const STANDARD_INSTRUMENT = 'iso-iec-27001-2022';
const STANDARD_OBLIGATION = 'iso-iec-27001-2022-conformance';

test.describe('standards in the library', () => {
  test("INV-S11: An edition of a standard is an instrument with public facts and no text", async ({ page, apiGuard }) => {
    // INV-S11 (INV-01, INV-02, INV-08). The API's bindingLevel and the single obligation
    // with no provision are proved by the backend's INV-S11 test; here, the screens.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openInstrument(page, STANDARD_INSTRUMENT);

    // "Standard" in the binding slot, as information, never "Guidance, comply or explain".
    // The level's label and the binding slot both read "Standard"; the third pill is the slot.
    const pills = headerPills(page);
    await expect(pills).toHaveText(['ISO/IEC 27001:2022', 'Standard', 'Standard', 'International', 'AI and ICT']);
    await expect(pills.nth(0)).toHaveAttribute('data-pill', 'brand');
    await expect(pills.nth(2)).toHaveAttribute('data-pill', 'information');

    // Public facts: the official reference, the publication date with its day precision
    // and "Standard" as the binding force. Library facts assert through a locator.
    const identity = page.locator('[data-identity-panel]');
    await expect(identity).toContainText('ISO/IEC 27001:2022');
    await expect(identity.getByText('In force from 25 Oct 2022')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Source' })).toHaveAttribute('href', /^https:\/\//);

    // No provision tree: the text is licensed, and the catalogue is one link away.
    const licensed = page.locator('[data-provision-tree] [data-provisions-licensed]');
    await expect(licensed.getByText('The text of this standard is licensed and not held here.')).toBeVisible();
    const catalogue = licensed.getByRole('link', { name: "See it in the publisher's catalogue" });
    await expect(catalogue).toHaveAttribute('href', /^https:\/\//);
    await expect(catalogue).toHaveAttribute('rel', /noopener/);

    // The one conformance duty, through the inventory's outside view: no seeded bank
    // follows the standard, so it is absent until "Show outside our scope", where its
    // row reads "Standard" and never "Guidance".
    await page.goto(`/inventory?regime=ai_ict&asOf=${AS_OF}`);
    const duty = page.locator(`[data-obligation="${STANDARD_OBLIGATION}"]`);
    await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(duty).toHaveCount(0);
    await page.getByRole('button', { name: 'Show outside our scope' }).click();
    await expect(duty).toHaveAttribute('data-outside-footprint', '');
    await expect(duty.locator('[data-pill]').filter({ hasText: /^Standard$/ })).toHaveCount(1);
    await expect(duty.locator('[data-pill]').filter({ hasText: /^Guidance$/ })).toHaveCount(0);

    await duty.click();
    const header = page.locator(`[data-obligation="${STANDARD_OBLIGATION}"] [data-header-pills] [data-pill]`);
    await expect(header.filter({ hasText: /^Standard$/ })).toHaveCount(1);
    await expect(header.filter({ hasText: /^Guidance, comply or explain$/ })).toHaveCount(0);
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
