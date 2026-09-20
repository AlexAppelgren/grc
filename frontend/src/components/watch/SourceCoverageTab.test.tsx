import { render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';
import { defaultFormatContext } from '@/shared/utils/format';

import type { SourceCoverage } from '@/features/watch/api';
import { coverageMeta, presentSourceCoverage } from '@/features/watch/coverage-presentation';
import { SourceCoverageTab } from './SourceCoverageTab';

// The Coverage tab (design/screens/tenant-watch.html, WAT-01): what the
// agents checked and how it went. The result's tone comes from the check's
// own kind and the stale marker from its slot, never from a sentence in the
// response.

const t = createT('en');
const ctx = defaultFormatContext;

const healthy: SourceCoverage = {
  source: {
    id: 's-1',
    name: 'fi.se',
    url: 'https://www.fi.se/',
    kind: { key: 'authority_site', kind: null, label: "Authority's own site" },
    authorityId: 'a-1',
    checkFrequency: 'daily',
    active: true,
  },
  lastCheckedAt: '2026-09-16T06:02:00Z',
  lastStatus: 'ok',
  lastError: null,
  overdue: false,
};

const stale: SourceCoverage = {
  ...healthy,
  source: { ...healthy.source, id: 's-2', name: 'skatteverket.se', checkFrequency: 'weekly' },
  lastStatus: 'failed',
  lastError: 'fetch failed, HTTP 503',
  overdue: true,
};

const untouched: SourceCoverage = {
  ...healthy,
  source: { ...healthy.source, id: 's-3', name: 'iso.org', checkFrequency: 'monthly', active: false },
  lastCheckedAt: null,
  lastStatus: 'never',
  lastError: null,
  overdue: false,
};

function renderTab(answer: () => { status: number; data?: unknown }): void {
  installAdapter(answer);
  const { wrapper: Query } = queryWrapper();
  const tree: ReactNode = (
    <Query>
      <LocaleProvider locale="en">
        <SourceCoverageTab active />
      </LocaleProvider>
    </Query>
  );
  render(tree);
}

describe('presentSourceCoverage', () => {
  it('the result takes its tone from the check’s kind', () => {
    expect(presentSourceCoverage(healthy, t).map((p) => [p.label, p.tone])).toEqual([
      ['Checked', 'positive'],
      ["Authority's own site", 'information'],
    ]);
    expect(presentSourceCoverage(stale, t)[0]).toMatchObject({ label: 'Fetch failed', tone: 'negative' });
    expect(presentSourceCoverage(untouched, t)[0]).toMatchObject({ label: 'Not checked', tone: 'information' });
  });

  it('a stale source is marked, between the result and the kind', () => {
    expect(presentSourceCoverage(stale, t).map((p) => p.key)).toEqual(['status:failed', 'stale', 'kind:authority_site']);
    expect(presentSourceCoverage(stale, t)[1]).toMatchObject({ label: 'Stale', tone: 'warning' });
  });

  it('a source left alone on purpose says so, and is neither stale nor failing', () => {
    const pills = presentSourceCoverage(untouched, t);
    expect(pills.map((p) => p.key)).toEqual(['status:never', 'kind:authority_site', 'paused']);
    expect(pills.at(-1)).toMatchObject({ label: 'Not checked automatically', tone: 'information' });
  });

  it('the meta line is the cadence promised and the last check that happened', () => {
    expect(coverageMeta(healthy, t, ctx)).toEqual(['Checked daily', 'Last checked 16 Sept 2026, 08:02']);
    expect(coverageMeta(stale, t, ctx)[0]).toBe('Checked weekly');
    expect(coverageMeta(untouched, t, ctx)).toEqual(['Checked monthly', 'No check logged yet']);
  });
});

describe('the Coverage tab', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('lists each source with its result, and names the failing check on a stale row', async () => {
    renderTab(() => ({ status: 200, data: [healthy, stale, untouched] }));
    await waitFor(() => expect(screen.getByText('fi.se')).toBeInTheDocument());
    const staleRow = screen.getByText('skatteverket.se').closest('li');
    expect(staleRow).not.toBeNull();
    expect(staleRow).toHaveAttribute('data-stale', '');
    expect(within(staleRow as HTMLElement).getByText('Fetch failed')).toHaveAttribute('data-pill', 'negative');
    expect(within(staleRow as HTMLElement).getByText('fetch failed, HTTP 503')).toBeInTheDocument();

    const healthyRow = screen.getByText('fi.se').closest('li');
    expect(healthyRow).not.toHaveAttribute('data-stale');
    expect(within(healthyRow as HTMLElement).getByText('Last checked 16 Sept 2026, 08:02')).toBeInTheDocument();
  });

  it('an empty registry is an answer, not a failure', async () => {
    renderTab(() => ({ status: 200, data: [] }));
    await waitFor(() => expect(screen.getByText('Nothing checked yet')).toBeInTheDocument());
  });

  it('a failed read offers to try again', async () => {
    renderTab(() => ({ status: 500 }));
    await waitFor(() => expect(screen.getByText('Could not load the coverage log')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('a server 403 renders the Restricted screen with what the server said', async () => {
    renderTab(() => ({ status: 403, data: { detail: 'You need the watch grant.', code: 'forbidden', requiredPermission: 'watch.read' } }));
    await waitFor(() => expect(screen.getByText('You need the watch grant.')).toBeInTheDocument());
    expect(screen.getByText('Needs watch read')).toBeInTheDocument();
  });

  it('the log is not read while the tab is closed', async () => {
    const sent = installAdapter(() => ({ status: 200, data: [] }));
    const { wrapper: Query } = queryWrapper();
    render(
      <Query>
        <LocaleProvider locale="en">
          <SourceCoverageTab active={false} />
        </LocaleProvider>
      </Query>,
    );
    await waitFor(() => expect(sent).toHaveLength(0));
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
