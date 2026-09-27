import { execFileSync } from 'node:child_process';
import path from 'node:path';

import type { Page, TestInfo } from '@playwright/test';

import { expect } from './api-guard';

// The bank's own records (OWN-01 to OWN-04; J-12, PRO-S15, INV-S15), as tenant A's
// journeys reach them. The seed (backend/apps/shared/e2e_seed.py, EXPECTED_OWN_RECORDS)
// leaves one regulation of tenant A's own in scope, its research running on the mock
// runner, and part 1's instrument and duties approved.

/** The seeded regulation's key, and what its research filed and the approver approved. */
export const SEEDED_REGULATION = 'lagen_om_vissa_kontanttjanster';
export const SEEDED_OWN_INSTRUMENT = 'own-lagen-om-vissa-kontanttjanster';
export const SEEDED_OWN_OBLIGATION = 'own-lagen-om-vissa-kontanttjanster-1';

export interface FiledProposal {
  id: string;
  kind: string;
  key: string;
  title: string;
}

/**
 * The mock runner reports what tenant A's own agent found for the scope item `item`
 * (`manage.py e2e_scope_findings`): part `part`'s instrument while the bank does not hold
 * it, its duties once a person approved it. The research opens on the outbox after the
 * approval, so the report is retried until the run is there. Reporting twice files nothing
 * twice.
 */
async function reportFindings(testInfo: TestInfo, item: string, part = 1): Promise<FiledProposal[]> {
  const script = path.join(testInfo.project.testDir, 'support', 'start-backend.sh').split(path.sep).join('/');
  let filed: FiledProposal[] = [];
  await expect(() => {
    const printed = execFileSync('bash', [script, 'manage', 'e2e_scope_findings', item, '--part', String(part)], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    filed = JSON.parse(printed) as FiledProposal[];
  }).toPass({ timeout: 90_000, intervals: [2_000, 5_000] });
  return filed;
}

function filedAt(filed: readonly FiledProposal[], index: number): FiledProposal {
  const row = filed[index];
  if (row === undefined) throw new Error(`the mock runner filed ${filed.length} proposals`);
  return row;
}

/** The mock runner's report while the bank does not hold part `part`: its own instrument. */
export async function reportInstrument(testInfo: TestInfo, item: string, part = 1): Promise<FiledProposal> {
  const filed = await reportFindings(testInfo, item, part);
  expect(filed.map((row) => row.kind)).toEqual(['new_instrument']);
  return filedAt(filed, 0);
}

/** The mock runner's report once the bank holds part `part`'s instrument: its two duties. */
export async function reportDuties(testInfo: TestInfo, item: string, part = 1): Promise<[FiledProposal, FiledProposal]> {
  const filed = await reportFindings(testInfo, item, part);
  expect(filed.map((row) => row.kind)).toEqual(['new_obligation', 'new_obligation']);
  return [filedAt(filed, 0), filedAt(filed, 1)];
}

/** Approve the bank's own proposal `proposalId` on its page, through the passkey prompt. */
export async function approveOwnProposal(page: Page, proposalId: string): Promise<void> {
  await page.goto(`/private-records/${proposalId}`);
  await page.locator('[data-private-decision]').getByRole('button', { name: 'Approve', exact: true }).click();
  await page.getByRole('dialog', { name: /^Approve ".+"\?$/ }).getByRole('button', { name: 'Approve with passkey' }).click();
  // Step-up: settle on the prompt or the outcome, since a sign-in moments ago may still count.
  const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
  const done = page.locator('[data-private-decided="approved"]');
  await expect(prompt.or(done).first()).toBeVisible();
  if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  await expect(done).toHaveText('Approved. It is in our inventory as Private to us.');
}
