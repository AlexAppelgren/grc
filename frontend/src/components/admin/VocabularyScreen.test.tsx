import type { AxiosAdapter } from 'axios';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { VocabularyScreen } from '@/components/admin/VocabularyScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { REFRESH_PATH, api, pathOf } from '@/shared/utils/api-client';

// A library list on the tenant surface lists what this bank itself proposed
// on it and is still waiting on (VOC-07, PRO-01), read from GET
// /tenant/proposals filtered to open proposals on this list. The console
// holds library lists too but never reads a bank's own proposals.

const LISTS_PATH = '/api/v1/vocab';
const VALUES_PATH = '/api/v1/vocab/flag';
const PENDING_PATH = '/api/v1/tenant/proposals';

const flags = { list: 'flag', tier: 2, kind: null, count: 1, retiredCount: 0, proposable: true };
const derivatives = {
  key: 'derivatives',
  kind: null,
  label: 'Derivatives',
  labels: { en: 'Derivatives' },
  usageNote: '',
  sortOrder: 1,
  active: true,
  isSystem: false,
  isDefault: false,
  usageCount: 0,
  extra: {},
};
const waiting = { id: 'p-1', kind: 'vocabulary_create', status: 'open', title: 'Add "Outsourcing" to flag', createdAt: '2026-09-16T07:12:00Z' };

/** The server: one library list with one value, and the bank's own proposals as `pending` answers. */
function server(pending: Answer): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === LISTS_PATH) return { status: 200, data: { items: [flags], total: 1 } };
    if (sent.path === VALUES_PATH) return { status: 200, data: { items: [derivatives], total: 1 } };
    if (sent.path === PENDING_PATH) return pending;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

async function renderScreen(surface: 'tenant' | 'console' = 'tenant'): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={['vocab.manage', 'proposals.create', 'library_vocab.manage']}>
        <VocabularyScreen list="flag" surface={surface} />
      </PermissionsProvider>
    </Query>,
  );
  await screen.findAllByText('Derivatives');
}

const pendingReads = (sent: Sent[]) => sent.filter((s) => s.path === PENDING_PATH);
const pendingPanel = () => document.querySelector('[data-pending-proposals]') as HTMLElement;

beforeEach(() => {
  resetApiForTests();
});

describe('what this bank proposed on a library list', () => {
  it('reads only open proposals on this list, and says so when none is waiting', async () => {
    const sent = server({ status: 200, data: { items: [], total: 0 } });
    await renderScreen();
    expect(await within(pendingPanel()).findByText('Nothing you suggested on this list is waiting for review.')).toBeVisible();
    expect(pendingReads(sent).map((s) => s.params)).toEqual([{ status: 'open', targetList: 'flag' }]);
  });

  it('shows a loading state until the answer comes', async () => {
    server({ status: 200, data: { items: [waiting], total: 1 } });
    // The pending read alone is held back until released; the rest answers at once.
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const scripted = api.defaults.adapter as AxiosAdapter;
    api.defaults.adapter = async (config) => {
      if (pathOf(config) === PENDING_PATH) await held;
      return scripted(config);
    };
    await renderScreen();
    expect(within(pendingPanel()).getByRole('status')).toHaveAttribute('aria-busy', 'true');
    release();
    expect(await within(pendingPanel()).findByText(waiting.title)).toBeVisible();
  });

  it('lists a waiting proposal by its title, marked as waiting, and not as a row of the list', async () => {
    server({ status: 200, data: { items: [waiting], total: 1 } });
    await renderScreen();
    const panel = pendingPanel();
    const row = (await within(panel).findByText(waiting.title)).closest('[data-pending-proposal]') as HTMLElement;
    expect(row).toHaveAttribute('data-pending-proposal', 'p-1');
    expect(within(row).getByText('Waiting for review')).toBeVisible();
    expect(document.querySelector('[data-vocabulary-values="flag"]')).not.toHaveTextContent('Outsourcing');
  });

  it('says so when the proposals cannot be read, and reads them again on retry', async () => {
    const sent = server({ status: 500, data: { code: 'server_error', detail: 'Boom.' } });
    await renderScreen();
    expect(await within(pendingPanel()).findByText('Your suggestions waiting for review could not be loaded.')).toBeVisible();
    fireEvent.click(within(pendingPanel()).getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(pendingReads(sent)).toHaveLength(2));
    // The rest of the screen stands: the list's own value is still shown.
    expect(screen.getAllByText('Derivatives')[0]).toBeVisible();
  });

  it('is never rendered, nor read, on the console surface', async () => {
    const sent = server({ status: 200, data: { items: [waiting], total: 1 } });
    await renderScreen('console');
    expect(pendingPanel()).toBeNull();
    expect(pendingReads(sent)).toHaveLength(0);
  });
});
