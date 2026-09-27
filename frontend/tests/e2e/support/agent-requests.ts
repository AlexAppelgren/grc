import type { Page } from '@playwright/test';

import { expect } from './api-guard';

// Research requests (AGT-05) as a person makes them on screen: a bank's admin on Agents
// asks one of the bank's own agents, and a library editor asks for a re-tag in the queue.
// Each returns the request the server answered with, read off the real response.

export interface AskedRequest {
  id: string;
  kind: string;
  status: string;
  tenantAgentId: string | null;
  topic: string | null;
}

async function answered(page: Page, path: string, submit: () => Promise<void>): Promise<AskedRequest> {
  const response = page.waitForResponse((r) => r.url().endsWith(path) && r.request().method() === 'POST');
  await submit();
  const answer = await response;
  expect(answer.status(), `${path} answered ${await answer.text()}`).toBe(202);
  return (await answer.json()) as AskedRequest;
}

/** Asks the bank's own agent on /admin/agents: check the source labelled `source`, or research `topic`. */
export async function askOurAgent(page: Page, ask: { source: string } | { topic: string }): Promise<AskedRequest> {
  const panel = page.locator('[data-research-panel]');
  // Tenant A runs two agents of its own; these requests are the source checker's.
  await panel.getByLabel('Which agent').selectOption({ label: 'Source checker' });
  if ('source' in ask) {
    await panel.getByLabel('Check this source now').check();
    await panel.getByLabel('Source', { exact: true }).selectOption({ label: ask.source });
  } else {
    await panel.getByLabel('Research a topic').check();
    await panel.getByLabel('Topic', { exact: true }).fill(ask.topic);
  }
  const request = await answered(page, '/api/v1/research-requests', () => panel.getByRole('button', { name: 'Ask', exact: true }).click());
  await expect(panel.getByText('Asked. The request is at the top of Our requests.')).toBeVisible();
  return request;
}

/** Asks bleqq's agent for a re-tag from the console queue: add the term labelled `term` to `records`. */
export async function askForRetag(page: Page, retag: { term: string; records: string }): Promise<AskedRequest> {
  await page.getByRole('button', { name: 'Ask for a re-tag' }).click();
  const form = page.locator('[data-retag-form]');
  await form.getByLabel('Term', { exact: true }).fill(retag.term);
  await form.getByLabel('Which obligations').fill(retag.records);
  return answered(page, '/api/v1/console/research-requests', () => form.getByRole('button', { name: 'Ask for the re-tag' }).click());
}
