import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ConsoleSourcesPage from '@/app/(console)/console/sources/page';
import { SourcesScreen } from '@/components/console/SourcesScreen';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The console's Sources page (WAT-01, ADM-02, ruling 3): the registry, its
// last checks, the three filters the card draws, and the two things this page
// must keep — it writes nothing, and it offers no control a console session
// could not pass.

const ME_PATH = '/api/v1/me';
const SOURCES_PATH = '/api/v1/sources';
const COVERAGE_PATH = '/api/v1/sources/coverage';
const AUTHORITIES_PATH = '/api/v1/authorities';

const NOW = new Date('2026-09-19T08:00:00Z');

const AUTHORITIES = [
  { id: 'a1', key: 'fi-se', shortName: 'FI', name: 'Finansinspektionen', jurisdiction: { key: 'se', kind: null, label: 'Sweden' }, url: 'https://www.fi.se/' },
  { id: 'a2', key: 'eurlex', shortName: 'EUR-Lex', name: 'Publications Office of the EU', jurisdiction: { key: 'eu', kind: null, label: 'EU' }, url: 'https://eur-lex.europa.eu/' },
];

const fi = { id: 's1', name: 'Finansinspektionen, publicerat', url: 'https://www.fi.se/sv/publicerat/', kind: { key: 'authority_site', kind: null, label: 'Authority site' }, authorityId: 'a1', checkFrequency: 'daily', active: true };
const eurlex = { id: 's2', name: 'EUR-Lex, Official Journal L series', url: 'https://eur-lex.europa.eu/oj/', kind: { key: 'official_journal', kind: null, label: 'Official journal' }, authorityId: 'a2', checkFrequency: 'daily', active: true };
const sweep = { id: 's3', name: 'Open web sweep, securities', url: null, kind: { key: 'open_web', kind: null, label: 'Open web sweep' }, authorityId: null, checkFrequency: 'weekly', active: false };

const COVERAGE = [
  { source: fi, lastCheckedAt: '2026-09-19T06:02:00Z', lastStatus: 'ok', lastError: null, overdue: false },
  { source: eurlex, lastCheckedAt: '2026-09-16T05:30:00Z', lastStatus: 'failed', lastError: 'HTTP 503', overdue: true },
  { source: sweep, lastCheckedAt: null, lastStatus: 'never', lastError: null, overdue: false },
];

const editor = {
  user: { id: 'u10', email: 'editor@bleqq.test', name: 'Ida Holm', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['proposals.review', 'library_vocab.manage', 'sources.manage', 'eval.manage'],
  platformRoles: [{ key: 'library_editor', kind: null, label: 'Library editor' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

function server(sources: Answer, coverage: Answer = { status: 200, data: COVERAGE }): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: editor };
    if (sent.path === AUTHORITIES_PATH) return { status: 200, data: AUTHORITIES };
    if (sent.path === COVERAGE_PATH) return coverage;
    if (sent.path === SOURCES_PATH && sent.method === 'get') return sources;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const rowOf = (id: string) => document.querySelector(`[data-source-id="${id}"]`) as HTMLElement;
const names = () => [...document.querySelectorAll('[data-source-id]')].map((el) => el.getAttribute('data-source-id'));

describe('console sources', () => {
  beforeEach(() => {
    resetApiForTests();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows every source with its kind, jurisdiction, cadence and last check', async () => {
    server({ status: 200, data: [fi, eurlex, sweep] });
    renderIn(<SourcesScreen />);
    await screen.findByText(fi.name);

    const healthy = rowOf('s1');
    expect(within(healthy).getByText('Authority site')).toBeInTheDocument();
    expect(within(healthy).getByText('Sweden')).toBeInTheDocument();
    expect(within(healthy).getByText('Checked')).toBeInTheDocument();
    expect(within(healthy).getByText('Checked daily')).toBeInTheDocument();
    expect(within(healthy).getByText('Finansinspektionen')).toBeInTheDocument();
    expect(within(healthy).getByText('Checked 19 Sept 2026, 08:02')).toBeInTheDocument();

    // A failing source says so, is marked stale, and shows what went wrong.
    const failing = rowOf('s2');
    expect(within(failing).getByText('Fetch failed')).toBeInTheDocument();
    expect(within(failing).getByText('Stale')).toBeInTheDocument();
    expect(within(failing).getByText('HTTP 503')).toBeInTheDocument();

    // A source deliberately left alone is not stale and not failing.
    const paused = rowOf('s3');
    expect(within(paused).getByText('Paused')).toBeInTheDocument();
    expect(within(paused).getByText('Not checked')).toBeInTheDocument();
    expect(within(paused).getByText('No check logged yet')).toBeInTheDocument();
    expect(within(paused).queryByText('Stale')).toBeNull();
  });

  it('counts how much of the registry is fresh and how much is not', async () => {
    server({ status: 200, data: [fi, eurlex, sweep] });
    renderIn(<SourcesScreen />);
    expect(await screen.findByText('1 of 3 checked in the last 24 h')).toBeInTheDocument();
    expect(screen.getByText('1 failing')).toBeInTheDocument();
  });

  it('filters by jurisdiction, by kind and to the failing rows', async () => {
    server({ status: 200, data: [fi, eurlex, sweep] });
    renderIn(<SourcesScreen />);
    await screen.findByText(fi.name);
    expect(names()).toEqual(['s1', 's2', 's3']);

    fireEvent.change(screen.getByLabelText('Jurisdiction'), { target: { value: 'eu' } });
    await waitFor(() => expect(names()).toEqual(['s2']));

    fireEvent.change(screen.getByLabelText('Jurisdiction'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'open_web' } });
    await waitFor(() => expect(names()).toEqual(['s3']));

    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Failing only' }));
    await waitFor(() => expect(names()).toEqual(['s2']));
  });

  it('is read-only: it writes nothing, and no control the console cannot pass is offered', async () => {
    const sent = server({ status: 200, data: [fi, eurlex, sweep] });
    renderIn(<SourcesScreen />);
    await screen.findByText(fi.name);

    expect(sent.every((s) => s.method === 'get' || s.path === REFRESH_PATH)).toBe(true);
    for (const label of ['Add a source', 'Edit', 'Pause', 'Resume', 'Check now', 'Re-check']) {
      expect(screen.queryByRole('button', { name: label })).toBeNull();
    }
  });

  it('says the registry is empty when nothing is registered', async () => {
    server({ status: 200, data: [] }, { status: 200, data: [] });
    renderIn(<SourcesScreen />);
    expect(await screen.findByText('No sources yet')).toBeInTheDocument();
  });

  it('offers a retry when the registry could not be read', async () => {
    server({ status: 500, data: { code: 'server_error', detail: 'no' } });
    renderIn(<SourcesScreen />);
    expect(await screen.findByText('Could not load the sources')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('is loading until both reads have answered', () => {
    server({ status: 200, data: [fi] });
    const { container } = renderIn(<SourcesScreen />);
    expect(container.querySelector('[data-loading-state]')).not.toBeNull();
  });

  it('shows the Restricted screen, naming the grant, to a console session without sources.manage', async () => {
    server({ status: 200, data: [] });
    renderIn(
      <PermissionsProvider permissions={['tenants.manage', 'agent_definitions.manage']}>
        <ConsoleSourcesPage />
      </PermissionsProvider>,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Needs sources manage');
  });
});
