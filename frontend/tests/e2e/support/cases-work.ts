import type { Locator, Page, TestInfo } from '@playwright/test';

import { expect } from './api-guard';

// Helpers for c9-e2e-triage-work: the triage and work journeys of the case panels (CAS-S2,
// CAS-S3, CAS-S4, CAS-S6, CAS-S7, CAS-S14, CAS-S19). Each journey spends its own seeded
// case (`seed_case_journeys` in backend/apps/shared/e2e_seed.py), so parallel workers never
// share one. A case's moves are append-only and cannot be rewound, so a journey that moves
// one first brings it back, through the same screens and the same state machine a person
// uses, to the category the seed left it in: a retry starts where the first attempt did.

/** The stable keys of the seeded cases these journeys work (`EXPECTED_CASE_JOURNEYS`). */
export const CASE_JOURNEYS = {
  triage: 'chg-e2e-case-triage',
  dismiss: 'chg-e2e-case-dismiss',
  assess: 'chg-e2e-case-assess',
  noAction: 'chg-e2e-case-assigned',
  actions: 'chg-e2e-case-actions',
  actionsLocked: 'chg-e2e-case-actions-locked',
  evidence: 'chg-e2e-case-evidence',
  secondBankLead: 'chg-e2e-second-bank-lead',
} as const;

/** The seeded people's names, as the owner picker and the audit log print them (`SEED_LOGINS`). */
export const PEOPLE = {
  officer: 'Sara Lindqvist',
  owner: 'Johan Berg',
  reader: 'Oskar Lund',
  secondBankOfficer: 'Søren Kristensen',
} as const;

/** The bank's own list values the journeys choose, as their seeded English labels. */
export const LABELS = {
  noActionReason: 'No action needed',
  notApplicableReason: 'Not applicable',
  outOfScope: 'Out of scope',
} as const;

/** Names what one attempt adds, so a retry (or a repeat) never meets the last attempt's rows. */
export function attemptOf(testInfo: TestInfo): string {
  return `${testInfo.repeatEachIndex + 1}.${testInfo.retry + 1}`;
}

/** The case's fixed category, as the change page's panels were drawn for it. */
export function casePanels(page: Page): Locator {
  return page.locator('[data-case-panels]');
}

/** The bearer the page itself sends, read from the first API request `navigate` makes. */
async function bearerOf(page: Page, navigate: () => Promise<unknown>): Promise<string> {
  const sent = page.waitForRequest((request) => request.url().includes('/api/v1/') && request.headers()['authorization'] !== undefined);
  await navigate();
  return (await sent).headers()['authorization'] ?? '';
}

/**
 * One call to the real API from inside the page, as the person signed in there: the request
 * passes through the page's network, so the API guard sees its answer.
 */
async function callApi(page: Page, authorization: string, method: string, path: string, body?: unknown): Promise<{ status: number; body: unknown }> {
  const url = `${process.env.E2E_BACKEND_URL ?? ''}/api/v1${path}`;
  return page.evaluate(
    async ({ url, method, authorization, body }) => {
      const headers: Record<string, string> = { authorization, 'content-type': 'application/json' };
      const response = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'include' });
      return { status: response.status, body: (await response.json().catch(() => null)) as unknown };
    },
    { url, method, authorization, body },
  );
}

/**
 * Opens the change page of a seeded case and answers the change's id. The feed's In progress
 * tab lists assigned cases only, so a case being assessed, implemented or signed off has no
 * row a person could click: the id is read from `GET /changes` (every tab, every footprint),
 * as the signed-in person, and the page is opened at its address.
 */
export async function openCase(page: Page, stableKey: string): Promise<string> {
  const authorization = await bearerOf(page, () => page.goto('/watch?scope=all'));
  for (let offset = 0; ; offset += 100) {
    const { body } = await callApi(page, authorization, 'GET', `/changes?tab=all&footprint=all&limit=100&offset=${offset}`);
    const feed = body as { items: { id: string; stableKey: string }[]; total: number };
    const found = feed.items.find((item) => item.stableKey === stableKey);
    if (found !== undefined) {
      await page.goto(`/watch/${found.id}`);
      await expect(casePanels(page)).toBeVisible();
      return found.id;
    }
    if (offset + 100 >= feed.total) throw new Error(`the feed has no seeded change ${stableKey}`);
  }
}

/**
 * Brings the open case back to "Needs triage" through the screen: a case assigned or being
 * assessed is closed with no action and moved back, a dismissed or one-person-closed case is
 * moved back. Needs a login holding cases.work and cases.triage (the compliance officer).
 */
export async function backToTriage(page: Page): Promise<void> {
  const category = await casePanels(page).getAttribute('data-case-panels');
  if (category === 'new') return;
  if (category === 'assigned' || category === 'assessing') {
    await page.locator('[data-case-panel="next-step"]').getByRole('button', { name: 'No action' }).click();
    const dialog = page.getByRole('dialog', { name: 'Close without action?' });
    await dialog.getByRole('radio', { name: LABELS.noActionReason }).check();
    await dialog.getByRole('button', { name: 'Close the case' }).click();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'closed');
  } else if (category !== 'closed' && category !== 'dismissed') {
    throw new Error(`a case in ${category} has no way back to triage`);
  }
  await page.getByRole('button', { name: 'Move back to triage' }).click();
  await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'new');
}

/** Triage from the open case's panel: the owner by name, the urgency by label when given. */
export async function triage(page: Page, owner: string, urgency?: string): Promise<void> {
  const panel = page.locator('[data-case-panel="triage"]');
  if (urgency !== undefined) await panel.getByLabel('Urgency').selectOption({ label: urgency });
  await panel.getByLabel('Owner').selectOption({ label: owner });
  await panel.getByRole('button', { name: 'Confirm and assign' }).click();
  await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'assigned');
}

/** Brings the open case back to "Assigned" to `owner`, as the seed left it, unless it already is. */
export async function assignedTo(page: Page, owner: string): Promise<void> {
  const nextStep = page.locator('[data-case-panel="next-step"]');
  if ((await casePanels(page).getAttribute('data-case-panels')) === 'assigned' && (await nextStep.getByText(`Assigned to ${owner} `).count()) > 0) return;
  await backToTriage(page);
  await triage(page, owner);
}

/** The header's pill carrying exactly this text; its tone is its `data-pill`. */
export function headerPill(page: Page, text: string): Locator {
  return page.locator('[data-change] > span [data-pill]').filter({ hasText: new RegExp(`^${text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) });
}

/** A plain date `days` after the bank's own today, in its own zone. */
export function tenantDay(days: number, timeZone = 'Europe/Stockholm'): string {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const date = new Date(`${today}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** A plain date as the screens print it for an English reader: "25 Oct 2026". */
export function shownDate(plain: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${plain}T00:00:00Z`));
}

/**
 * Sends one write to the real API as the person signed in, and answers its status and
 * problem code: for a refusal no control on screen can provoke, because the screen already
 * shows the lock and offers no control that would send it. The journey declares it.
 */
export async function writeAsSignedIn(page: Page, method: 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<{ status: number; code: string | null }> {
  const authorization = await bearerOf(page, () => page.reload());
  await expect(casePanels(page)).toBeVisible();
  const answer = await callApi(page, authorization, method, path, body);
  return { status: answer.status, code: (answer.body as { code?: string } | null)?.code ?? null };
}

/**
 * Opens the audit log at one record's history: filtered to the record kind, then to the
 * record of the newest row with this action that carries `text` (a subject id or a title),
 * with "Only this record". Answers the rows now shown, every one that record's.
 */
export async function recordHistory(page: Page, subjectType: string, action: string, text: string): Promise<Locator> {
  await page.goto('/admin/audit-log');
  await expect(page.getByRole('heading', { level: 1, name: 'Audit log' })).toBeVisible();
  await page.getByLabel('Record kind').selectOption(subjectType);
  const rows = page.locator(`[data-audit-row][data-subject-type="${subjectType}"][data-action="${action}"]`);
  const newest = rows.and(page.locator(`[data-subject-id="${text}"]`)).or(rows.filter({ hasText: text }));
  await newest.first().locator('[data-only-record]').click();
  await expect(page.locator('[data-clear-record]')).toBeVisible();
  return page.locator('[data-audit-row]');
}
