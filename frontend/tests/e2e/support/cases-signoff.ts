import type { Download, Locator, Page } from '@playwright/test';

import { expect, type ApiGuard } from './api-guard';

// Helpers for the sign-off journeys and J-3 (c9-e2e-signoff-j3; CAS-S8 to CAS-S11,
// CAS-S15). Each journey spends a case of its own from apps/shared/e2e_seed.py
// (EXPECTED_CASE_JOURNEYS), so parallel workers never share one. A signed-off case can
// never be reopened (the state machine's closed is final), so a retry settles on the
// state the first attempt reached rather than restoring it.

export interface SeededCase {
  stableKey: string;
  title: string;
}

// e2e_seed.py EXPECTED_CASE_JOURNEYS, by journey.
export const CASES = {
  s8: { stableKey: 'chg-e2e-case-signoff-guards', title: 'Riksgälden fixes the government borrowing rate used for ISK and KF tax' },
  s9: { stableKey: 'chg-e2e-case-self-signoff', title: 'FI amends the rules on client categorisation' },
  s10: { stableKey: 'chg-e2e-case-signoff', title: 'ESMA updates its guidelines on product governance' },
  s11: { stableKey: 'chg-e2e-case-file', title: 'FI adopts new rules on reporting best execution' },
  j3: { stableKey: 'chg-e2e-case-j3', title: 'FI consults on sustainability preferences in the suitability assessment' },
} as const satisfies Record<string, SeededCase>;

// The seeded people's display names (apps/shared/e2e_logins.py).
export const NAMES = {
  owner: 'Johan Berg',
  approver: 'Maria Ek',
  ownerApprover: 'Emma Lindberg',
} as const;

const APPROVE = /\/api\/v1\/changes\/[^/]+\/signoff\/approve$/;

/** The case panels have settled when the panels of a known category are on screen. */
export function casePanels(page: Page): Locator {
  return page.locator('[data-case-panels]');
}

/**
 * Opens the change page of a seeded case from Search, which finds every registered change by
 * its title. The feed would be the natural way in, but its "In progress" tab lists assigned
 * cases only, so a case being implemented or waiting for sign-off is on no tab of it.
 */
export async function openCase(page: Page, seeded: SeededCase): Promise<void> {
  await page.goto('/search');
  await page.getByRole('searchbox', { name: 'Search' }).fill(seeded.title);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.locator('a[data-hit-type="change"]').filter({ hasText: seeded.title }).first().click();
  await expect(page.locator(`[data-change="${seeded.stableKey}"]`)).toBeVisible();
  await expect(casePanels(page)).toBeVisible();
}

/** Tenant A's own date `days` from today, as a date input takes it (tenant A keeps Stockholm time). */
export function tenantDate(days: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm' }).format(new Date(Date.now() + days * 86_400_000));
}

/** A small, well-formed PDF, the evidence J-3 attaches. */
export function evidencePdf(name: string): { name: string; mimeType: string; buffer: Buffer } {
  const body = `%PDF-1.4\n% J-3 evidence: ${name}\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n`;
  return { name, mimeType: 'application/pdf', buffer: Buffer.from(body) };
}

/** The shared passkey prompt the api client opens on 403 `step_up_required`. */
export async function passStepUp(page: Page): Promise<void> {
  const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
  await expect(prompt).toBeVisible();
  await prompt.getByRole('button', { name: 'Use passkey' }).click();
  await expect(prompt).toHaveCount(0);
}

/**
 * "Sign off and close" on a case waiting for sign-off. The first attempt answers 403
 * `step_up_required`, which opens the passkey prompt; the api client sends it once more
 * with the fresh assertion. Resolves with the approval's final answer.
 */
export async function signOffAndClose(page: Page, apiGuard: ApiGuard): Promise<{ status: number; body: { id?: string; code?: string } }> {
  apiGuard.allow(APPROVE, 403, 'the approval answers step_up_required first and opens the passkey prompt');
  const answered = page.waitForResponse((r) => APPROVE.test(new URL(r.url()).pathname) && r.status() !== 403);
  await page.locator('[data-signoff-panel="signoff"]').getByRole('button', { name: 'Sign off and close' }).click();
  await passStepUp(page);
  const response = await answered;
  return { status: response.status(), body: (await response.json()) as { id?: string; code?: string } };
}

/** Opens "Show case file" and returns the dialog once the text is in. */
export async function showCaseFile(page: Page): Promise<Locator> {
  await page.locator('[data-case-file-panel]').getByRole('button', { name: 'Show case file' }).click();
  const dialog = page.getByRole('dialog', { name: 'Case file' });
  await expect(dialog.locator('[data-case-file-text]')).toBeVisible();
  return dialog;
}

/** The case file's lines as the screen shows them: each heading and each line, in order. */
export async function caseFileLines(dialog: Locator): Promise<string[]> {
  const lines = await dialog.locator('[data-case-file-text] h3, [data-case-file-text] p').allTextContents();
  return lines.map((line) => line.trim()).filter((line) => line !== '');
}

/** A downloaded case file's lines, the headings' underlines and the blank lines left out, as the screen sets them. */
export async function downloadedLines(download: Download): Promise<string[]> {
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk as Uint8Array));
  const text = Buffer.concat(chunks).toString('utf8');
  return text
    .split('\n')
    .filter((line, index, all) => !(/^=+$/.test(line) && (all[index - 1] ?? '').length === line.length))
    .map((line) => line.trim())
    .filter((line) => line !== '');
}

/** The part of an obligation's page the library and the register own, read as text. */
export async function obligationFacts(page: Page, obligationHref: string): Promise<string> {
  await page.goto(obligationHref);
  const panels = page.locator('[data-identity-panel], [data-duty-panel], [data-scope-panel], [data-versions-panel]');
  await expect(panels.first()).toBeVisible();
  await expect(page.locator('[data-loading-state]')).toHaveCount(0);
  return (await panels.allInnerTexts()).join('\n---\n');
}
