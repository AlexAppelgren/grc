import type { QueryClient } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AdminGate } from '@/components/admin/AdminGate';
import type { Me } from '@/features/identity/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';
import { defaultFormatContext, formatDate } from '@/shared/utils/format';

import { FootprintScreen } from './FootprintScreen';

// /admin/footprint (design/screens/admin-footprint.html, states 1 to 16): the
// scope opens read-only, "Propose a change" turns it into checkboxes with a
// change panel, a waiting request marks the terms it changes, a second person
// decides in a dialog, and every send and decision moves focus to the status line.
// Under it, states 17 to 19: the markets we operate in and watch, with a Watching
// toggle that saves at once, and the request history one page at a time.

const ME = '/api/v1/me';
const FOOTPRINT = '/api/v1/tenant/footprint';
const REQUESTS = `${FOOTPRINT}/requests`;
const TERMS = '/api/v1/taxonomy/terms';
const JURISDICTIONS = '/api/v1/reference/jurisdictions';
const WATCHING = `${FOOTPRINT}/watching`;

const REQUEST_AND_APPROVE = ['footprint.request', 'footprint.approve'];
const SARA = { id: 'u1', name: 'Sara Lindqvist' };
const MARIA = { id: 'u2', name: 'Maria Ek' };
const ERIK = { id: 'u3', name: 'Erik Holm' };

function meOf(user: { id: string; name: string }, permissions: readonly string[]): Me {
  return {
    user: { id: user.id, email: `${user.id}@example.test`, name: user.name, locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
    roles: [],
    permissions: [...permissions],
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 1,
    stepUpValidUntil: null,
    counts: { triage: 0, proposals: 0, assignedToMe: 0, unreadNotifications: 0 },
    lastVisitAt: null,
    notificationPrefs: null,
    headOf: [],
  } as Me;
}

const held = (key: string, label: string) => ({ key, kind: null, label });
const dimension = (key: string, label: string, terms: ReturnType<typeof held>[], restrictsFootprint = true) => ({
  dimension: { key, kind: null, label },
  restrictsFootprint,
  allSelected: false,
  terms,
});

const DIMENSIONS = [
  dimension('regime', 'Regime', [held('securities', 'Securities')]),
  dimension('service_type', 'Service', [held('advice', 'Advice'), held('custody', 'Custody')]),
  dimension('client_category', 'Client category', []),
  dimension('product_type', 'Product type', []),
  dimension('channel', 'Channel', [held('digital', 'Digital')], false),
  dimension('jurisdiction', 'Jurisdiction', [held('se', 'Sweden')]),
];

type Level = 'operating' | 'watching' | 'not_followed';
const country = (key: string, label: string, level: Level) => ({ jurisdiction: { key, kind: 'country', label }, level });
const MARKETS = [country('se', 'Sweden', 'operating'), country('dk', 'Denmark', 'watching'), country('no', 'Norway', 'watching'), country('fi', 'Finland', 'not_followed')];
const REFERENCE = [
  { key: 'eu', kind: 'supranational', label: 'European Union', parentKey: null },
  ...MARKETS.map((m) => ({ key: m.jurisdiction.key, kind: 'country', label: m.jurisdiction.label, parentKey: 'eu' })),
];

function scope(pendingRequest: unknown = null, dimensions: unknown[] = DIMENSIONS, markets: unknown[] = MARKETS) {
  return { dimensions, pendingRequest, markets };
}

// A jurisdiction term mirrors a jurisdiction row; the screen knows its group by that, never by the dimension's key.
const term = (dimensionKey: string, key: string, label: string) => ({ id: `${dimensionKey}:${key}`, dimension: { key: dimensionKey, kind: null, label: dimensionKey }, key, kind: null, label, usageNote: '', sortOrder: 0, active: true, mirrored: dimensionKey === 'jurisdiction' });
const TAXONOMY = {
  items: [
    term('regime', 'securities', 'Securities'),
    term('regime', 'insurance', 'Insurance'),
    term('service_type', 'advice', 'Advice'),
    term('service_type', 'custody', 'Custody'),
    term('service_type', 'insurance_distribution', 'Insurance distribution'),
    term('client_category', 'retail', 'Retail'),
    term('client_category', 'professional', 'Professional'),
    term('channel', 'digital', 'Digital'),
    term('jurisdiction', 'se', 'Sweden'),
    term('jurisdiction', 'dk', 'Denmark'),
  ],
  total: 10,
};

const REQUESTED_AT = '2026-09-18T12:00:00Z';
const retail = { dimension: 'client_category', key: 'retail', kind: null, label: 'Retail' };
const advice = { dimension: 'service_type', key: 'advice', kind: null, label: 'Advice' };

function waiting(requestedBy: { id: string; name: string } = SARA) {
  return {
    id: 'r1',
    status: 'pending',
    requestedAt: REQUESTED_AT,
    requestedBy,
    adds: [retail],
    removes: [advice],
    preview: { obligations: { hidden: 2, revealed: 1, available: true }, cases: { hidden: 0, revealed: 0, available: false } },
    decidedBy: null,
    decidedAt: null,
    decisionNote: '',
    version: 3,
  };
}

const HISTORY = {
  items: [
    {
      ...waiting(),
      id: 'r0',
      status: 'rejected',
      adds: [],
      removes: [{ dimension: 'regime', key: 'tax', kind: null, label: 'Tax' }],
      decidedBy: MARIA,
      decidedAt: '2026-09-02T09:40:00Z',
      decisionNote: 'ISK tax reporting is ours.',
    },
  ],
  total: 1,
};

type Server = { pending: unknown; dimensions: unknown[]; markets: ReturnType<typeof country>[] };
type Mutation = (sent: Sent, server: Server) => Answer;

/** The server for one test: reads answer from `server`, and each write is the test's own script. */
function serve(me: Me, pending: unknown = null, write: Mutation = () => ({ status: 500 }), taxonomy = TAXONOMY): { sent: Sent[]; server: Server } {
  const server: Server = { pending, dimensions: DIMENSIONS, markets: MARKETS };
  const sent = installAdapter((s) => {
    if (s.path === ME) return { status: 200, data: me };
    if (s.path === FOOTPRINT) return { status: 200, data: scope(server.pending, server.dimensions, server.markets) };
    if (s.path === TERMS) return { status: 200, data: taxonomy };
    if (s.path === JURISDICTIONS) return { status: 200, data: REFERENCE };
    if (s.method === 'get' && s.path === REQUESTS) return { status: 200, data: HISTORY };
    return write(s, server);
  });
  return { sent, server };
}

/** The dry run answers with counts; a real send stores the request as waiting. */
function preview(hidden: number, revealed: number): Mutation {
  return (s, server) => {
    if (s.method === 'post' && s.path === REQUESTS && (s.params as { dryRun?: boolean } | null)?.dryRun === true) {
      return { status: 200, data: { dryRun: true, preview: { obligations: { hidden, revealed, available: true }, cases: { hidden: 0, revealed: 0, available: false } } } };
    }
    if (s.method === 'post' && s.path === REQUESTS) {
      server.pending = { ...waiting(), adds: [], removes: [advice] };
      return { status: 201, data: server.pending };
    }
    return { status: 500 };
  };
}

function shell(children: ReactNode, permissions: readonly string[]): { node: ReactNode; queryClient: QueryClient } {
  const { wrapper: Query, queryClient } = queryWrapper();
  return {
    node: (
      <Query>
        <PermissionsProvider permissions={permissions}>
          <LocaleProvider locale="en">{children}</LocaleProvider>
        </PermissionsProvider>
      </Query>
    ),
    queryClient,
  };
}

/** Renders the screen; the query client lets a test read the scope again, as a refetch on reconnect would. */
function open(me: Me): QueryClient {
  const { node, queryClient } = shell(<FootprintScreen />, me.permissions);
  render(node);
  return queryClient;
}

async function readScopeAgain(queryClient: QueryClient): Promise<void> {
  await act(() => queryClient.invalidateQueries({ queryKey: ['tenant', 'footprint'] }));
}

const group = (key: string) => document.querySelector<HTMLElement>(`[data-dimension="${key}"]`)!;
const item = (dimensionKey: string, key: string) => group(dimensionKey).querySelector<HTMLElement>(`[data-term="${key}"]`)!;
const statusLine = () => document.querySelector<HTMLElement>('[data-status-line]')!;

/** The waiting request's banner, once the scope has been read. */
function findBanner(): Promise<HTMLElement> {
  return waitFor(() => {
    const banner = document.querySelector<HTMLElement>('[data-pending-request]');
    if (banner === null) throw new Error('no banner yet');
    return banner;
  });
}

/** All text inside a warn notice is the text colour: muted and negative both fail AA on the dark warning fill. */
function expectWarnNoticesInTextColour(): void {
  for (const notice of document.querySelectorAll('[data-notice="warn"]')) {
    expect(notice.querySelectorAll('.text-muted, .text-negative')).toHaveLength(0);
  }
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

describe('FootprintScreen: the read state', () => {
  it('opens read-only: every option a glyph with its state in words, no checkbox, one group per restricting dimension with an active term', async () => {
    serve(meOf(SARA, REQUEST_AND_APPROVE));
    open(meOf(SARA, REQUEST_AND_APPROVE));

    expect(await screen.findByRole('heading', { level: 1, name: 'Regulatory scope' })).toBeVisible();
    expect(await screen.findByText('Which rules apply to us, what we do and for whom')).toBeVisible();
    await waitFor(() => expect(group('service_type')).not.toBeNull());
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    // Channel never restricts; product type has no active term.
    expect([...document.querySelectorAll('[data-dimension]')].map((node) => node.getAttribute('data-dimension'))).toEqual(['regime', 'service_type', 'client_category', 'jurisdiction']);
    expect(within(group('service_type')).getByRole('heading', { level: 3, name: 'Service' })).toBeVisible();
    expect(item('service_type', 'advice')).toHaveTextContent('Advice In our scope');
    expect(item('service_type', 'insurance_distribution')).toHaveTextContent('Insurance distribution Not in our scope');
    expect(item('service_type', 'advice').querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    // An empty group is the unrestricted one, said once instead of a list.
    expect(within(group('client_category')).getByText('Not restricted: every option applies.')).toBeVisible();
    expect(group('client_category').querySelector('[data-term]')).toBeNull();
    expect(within(group('jurisdiction')).getByText('The markets we operate in.')).toBeVisible();

    expect(screen.getByText('Changes apply to every member once someone else approves them with a passkey.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Propose a change' })).toBeEnabled();
    expect(statusLine()).toBeEmptyDOMElement();
    expect(statusLine()).toHaveAttribute('role', 'status');
    expect(statusLine()).toHaveAttribute('tabindex', '-1');

    const history = document.querySelector<HTMLElement>('[data-footprint-history]')!;
    expect(await within(history).findByText('rejected "Remove Tax" requested by Sara Lindqvist: "ISK tax reporting is ours."')).toBeVisible();
    expect(within(history).getByText('Maria Ek')).toBeVisible();
  });

  it('keeps a held term that is no longer active: it reads as held, its group still filters, and it can be unticked', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    // The seed took Sweden's term inactive with its jurisdiction; the scope still holds it.
    const inactiveSweden = { ...TAXONOMY, items: TAXONOMY.items.filter((row) => row.key !== 'se' && row.key !== 'dk') };
    serve(me, null, preview(0, 0), inactiveSweden);
    open(me);
    await waitFor(() => expect(group('jurisdiction')).not.toBeNull());
    expect(item('jurisdiction', 'se')).toHaveTextContent('Sweden In our scope');
    expect(within(group('jurisdiction')).queryByText('Not restricted: every option applies.')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Propose a change' }));
    const sweden = await screen.findByRole('checkbox', { name: 'Sweden' });
    expect(sweden).toBeChecked();
    fireEvent.click(sweden);
    const panel = document.querySelector<HTMLElement>('[data-draft-preview]')!;
    expect(within(panel).getByRole('heading', { name: 'Your change: Remove Sweden' })).toBeVisible();
  });

  it('reads the same for someone who can only approve, without "Propose a change"', async () => {
    const me = meOf(MARIA, ['footprint.approve']);
    serve(me);
    open(me);
    await waitFor(() => expect(group('service_type')).not.toBeNull());
    expect(screen.queryByRole('button', { name: 'Propose a change' })).toBeNull();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(screen.getByText('Changes apply to every member once someone else approves them with a passkey.')).toBeVisible();
  });
});

// std-journeys (FP-S16; FP-01, INV-08, AC-FP3): an opt-in group holds the standards a bank
// follows. Empty, it hides every record of a standard, so it never reads "not restricted".
describe('FootprintScreen: the standards a bank follows', () => {
  const STANDARDS = { dimension: { key: 'standard', kind: 'opt_in', label: 'Standards followed' }, restrictsFootprint: true, allSelected: false, terms: [] };
  const WITH_STANDARDS = { ...TAXONOMY, items: [...TAXONOMY.items, term('standard', 'iso_iec_27001', 'ISO/IEC 27001')], total: TAXONOMY.total + 1 };

  it('reads an empty opt-in group as none followed, in the read and the edit state, and following one warns of no narrowing', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { server } = serve(me, null, preview(0, 1), WITH_STANDARDS);
    server.dimensions = [...DIMENSIONS, STANDARDS];
    open(me);
    await waitFor(() => expect(group('standard')).not.toBeNull());
    expect(within(group('standard')).getByRole('heading', { level: 3, name: 'Standards followed' })).toBeVisible();
    expect(within(group('standard')).getByText('None followed.')).toBeVisible();
    expect(within(group('standard')).queryByText('Not restricted: every option applies.')).toBeNull();
    expect(group('standard').querySelector('[data-term]')).toBeNull();
    // A scope group with nothing held still reads as unrestricted.
    expect(within(group('client_category')).getByText('Not restricted: every option applies.')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Propose a change' }));
    expect(await screen.findByRole('group', { name: 'Standards followed' })).toHaveAccessibleDescription('None followed.');
    fireEvent.click(screen.getByRole('checkbox', { name: 'ISO/IEC 27001' }));
    const panel = document.querySelector<HTMLElement>('[data-draft-preview]')!;
    expect(within(panel).getByRole('heading', { name: 'Your change: Add ISO/IEC 27001' })).toBeVisible();
    expect(await within(panel.querySelector<HTMLElement>('[data-preview-side="reveals"]')!).findByText('1 obligation')).toBeVisible();
    // Following a standard only reveals: no group starts to filter, and nothing is hidden.
    expect(panel.querySelector('[data-notice="warn"]')).toBeNull();
    expect(screen.getByRole('group', { name: 'Standards followed' })).not.toHaveAccessibleDescription('None followed.');
  });

  it('lists a followed standard as held', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { server } = serve(me, null, undefined, WITH_STANDARDS);
    server.dimensions = [...DIMENSIONS, { ...STANDARDS, terms: [held('iso_iec_27001', 'ISO/IEC 27001')] }];
    open(me);
    await waitFor(() => expect(group('standard')).not.toBeNull());
    expect(item('standard', 'iso_iec_27001')).toHaveTextContent('ISO/IEC 27001 In our scope');
    expect(within(group('standard')).queryByText('None followed.')).toBeNull();
  });
});

describe('FootprintScreen: proposing a change', () => {
  it('turns the groups into checkboxes with the focus on the first, and one Cancel that returns to "Propose a change"', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    serve(me, null, preview(0, 0));
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));

    await waitFor(() => expect(document.activeElement).toBe(screen.getAllByRole('checkbox')[0]));
    expect(screen.getByRole('checkbox', { name: 'Securities' })).toBe(document.activeElement);
    expect(screen.queryByRole('button', { name: 'Propose a change' })).toBeNull();
    expect(within(group('service_type')).getByRole('checkbox', { name: 'Advice' })).toBeChecked();
    expect(within(group('service_type')).getByRole('checkbox', { name: 'Insurance distribution' })).not.toBeChecked();
    // The hint sits under the legend and describes the group, so the rule is heard before the options.
    expect(screen.getByRole('group', { name: 'Client category' })).toHaveAccessibleDescription('Not restricted: every option applies.');
    expect(screen.getByRole('group', { name: 'Jurisdiction' })).toHaveAccessibleDescription('The markets we operate in.');

    const panel = document.querySelector<HTMLElement>('[data-draft-preview]')!;
    expect(within(panel).getByRole('heading', { name: 'Your change' })).toBeVisible();
    expect(within(panel).getByText('Nothing changed yet.')).toBeVisible();
    expect(screen.getAllByRole('button', { name: 'Cancel' })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Request approval' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Propose a change' })));
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(document.querySelector('[data-draft-preview]')).toBeNull();
  });

  it('previews a widening change without a warning, and warns once a group starts to filter', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { sent } = serve(me, null, preview(0, 1));
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Insurance distribution' }));
    const panel = document.querySelector<HTMLElement>('[data-draft-preview]')!;
    expect(within(panel).getByRole('heading', { name: 'Your change: Add Insurance distribution' })).toBeVisible();
    const reveals = panel.querySelector<HTMLElement>('[data-preview-side="reveals"]')!;
    expect(await within(reveals).findByText('1 obligation')).toBeVisible();
    // Nothing counted is hidden, so there is nothing to warn about.
    expect(within(panel.querySelector<HTMLElement>('[data-preview-side="hides"]')!).getByText('0 obligations')).toBeVisible();
    expect(panel.querySelector('[data-notice="warn"]')).toBeNull();
    expect(sent.filter((s) => s.method === 'post').at(-1)).toMatchObject({ path: REQUESTS, params: { dryRun: true }, body: { adds: [{ dimension: 'service_type', key: 'insurance_distribution' }], removes: [] } });

    fireEvent.click(screen.getByRole('checkbox', { name: 'Retail' }));
    expect(within(panel).getByRole('heading', { name: 'Your change: Add Insurance distribution and Retail' })).toBeVisible();
    const warning = panel.querySelector<HTMLElement>('[data-notice="warn"]')!;
    expect(within(warning).getByText('What this hides leaves the feed, the inventory, the roadmap and the briefing for every member.')).toBeVisible();
    expect(within(warning).getByText('Client category will start to filter: records tagged only with other options in it are hidden from every member.')).toBeVisible();
    // Retail now restricts the group, so its hint no longer says it does not.
    expect(screen.getByRole('group', { name: 'Client category' })).not.toHaveAccessibleDescription('Not restricted: every option applies.');
    expectWarnNoticesInTextColour();
    expect(screen.getAllByRole('button', { name: 'Cancel' })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Request approval' })).toBeEnabled();
  });

  it('warns when the counted part hides something', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    serve(me, null, preview(2, 0));
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Advice' }));
    const panel = document.querySelector<HTMLElement>('[data-draft-preview]')!;
    expect(await within(panel.querySelector<HTMLElement>('[data-preview-side="hides"]')!).findByText('2 obligations')).toBeVisible();
    const warning = panel.querySelector<HTMLElement>('[data-notice="warn"]')!;
    expect(within(warning).getByText('What this hides leaves the feed, the inventory, the roadmap and the briefing for every member.')).toBeVisible();
    expect(within(warning).queryByText(/will start to filter/)).toBeNull();
    // Emptying a group widens the scope; its hint says so.
    fireEvent.click(screen.getByRole('checkbox', { name: 'Custody' }));
    expect(screen.getByRole('group', { name: 'Service' })).toHaveAccessibleDescription('Not restricted: every option applies.');
  });

  it('ends the edit for good when another request starts waiting, so the old draft never comes back once it is decided', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { server } = serve(me, null, preview(0, 1));
    const queryClient = open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Insurance distribution' }));
    expect(within(document.querySelector<HTMLElement>('[data-draft-preview]')!).getByRole('heading', { name: 'Your change: Add Insurance distribution' })).toBeVisible();

    // Erik's request arrives while Sara edits: the edit ends and the focus lands on the banner that says why.
    server.pending = waiting(ERIK);
    await readScopeAgain(queryClient);
    const banner = await findBanner();
    await waitFor(() => expect(document.activeElement).toBe(banner));
    expect(document.querySelector('[data-draft-preview]')).toBeNull();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);

    // Decided elsewhere: the page returns to the read state, not to Sara's old snapshot.
    server.pending = null;
    await readScopeAgain(queryClient);
    expect(await screen.findByRole('button', { name: 'Propose a change' })).toBeVisible();
    expect(document.querySelector('[data-draft-preview]')).toBeNull();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('ends the edit when the stored scope changes under it, so the diff never proposes to undo that change', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { server } = serve(me, null, preview(0, 1));
    const queryClient = open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Insurance distribution' }));

    // Someone's "Remove Advice" was approved between two reads, so no waiting request was ever seen here.
    server.dimensions = DIMENSIONS.map((d) => (d.dimension.key === 'service_type' ? { ...d, terms: [held('custody', 'Custody')] } : d));
    await readScopeAgain(queryClient);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Propose a change' })));
    expect(document.querySelector('[data-draft-preview]')).toBeNull();
    expect(item('service_type', 'advice')).toHaveTextContent('Advice Not in our scope');

    // A new draft starts from today's scope: nothing differs, so nothing proposes to add Advice back.
    fireEvent.click(screen.getByRole('button', { name: 'Propose a change' }));
    expect(within(document.querySelector<HTMLElement>('[data-draft-preview]')!).getByText('Nothing changed yet.')).toBeVisible();
    expect(within(group('service_type')).getByRole('checkbox', { name: 'Advice' })).not.toBeChecked();
  });

  it('says under the banner that someone else got in first when the send finds a request already waiting', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const dryRun = preview(1, 0);
    const { sent } = serve(me, null, (s, server) => {
      if (s.method === 'post' && s.path === REQUESTS && s.params === null) {
        server.pending = waiting(ERIK);
        return { status: 409, data: { code: 'request_pending', detail: 'A change is already waiting for a decision.' } };
      }
      return dryRun(s, server);
    });
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Advice' }));
    fireEvent.click(screen.getByRole('button', { name: 'Request approval' }));

    const banner = await findBanner();
    expect(within(banner).getByText('Add Retail, remove Advice')).toBeVisible();
    await waitFor(() => expect(document.activeElement).toBe(banner));
    const refusal = screen.getByRole('alert');
    expect(refusal).toHaveTextContent('Someone else proposed a change first, so yours was not sent.');
    expect(refusal.closest('[data-pending-request]')).toBeNull();
    expect(document.querySelector('[data-draft-preview]')).toBeNull();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(statusLine()).toBeEmptyDOMElement();
    expect(sent.filter((s) => s.method === 'post' && s.params === null)).toHaveLength(1);
  });

  it('sends the draft, shows it waiting with its marks, and moves the focus to the status line', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { sent } = serve(me, null, preview(1, 0));
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Advice' }));
    fireEvent.click(screen.getByRole('button', { name: 'Request approval' }));

    await waitFor(() => expect(document.activeElement).toBe(statusLine()));
    expect(statusLine()).toHaveTextContent('Sent for approval.');
    expect(sent.filter((s) => s.method === 'post' && s.params === null)).toEqual([expect.objectContaining({ path: REQUESTS, body: { adds: [], removes: [{ dimension: 'service_type', key: 'advice' }] } })]);
    const banner = await findBanner();
    expect(within(banner).getByText('Remove Advice')).toBeVisible();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(item('service_type', 'advice')).toHaveTextContent('Removed when approved');
  });
});

describe('FootprintScreen: a waiting request', () => {
  it("shows the requester their request, its marks on the terms and Withdraw, and focuses the status line after withdrawing", async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { sent } = serve(me, waiting(SARA), (s, server) => {
      if (s.path === `${REQUESTS}/r1/withdraw`) {
        server.pending = null;
        return { status: 200, data: { ...waiting(), status: 'withdrawn' } };
      }
      return { status: 500 };
    });
    open(me);

    const banner = await findBanner();
    expect(within(banner).getByText('Waiting for approval')).toBeVisible();
    expect(within(banner).getByText('Add Retail, remove Advice')).toBeVisible();
    expect(await within(banner).findByText(`You requested this on ${formatDate(REQUESTED_AT, { ...defaultFormatContext, timeZone: 'Europe/Stockholm' })}.`)).toBeVisible();
    expect(within(banner).getByText('No other change can be proposed until this one is decided.')).toBeVisible();
    expect(within(banner).queryByRole('button', { name: 'Approve' })).toBeNull();
    expectWarnNoticesInTextColour();
    // One warn notice at most above the groups: the banner replaces the rule.
    expect(screen.queryByText('Changes apply to every member once someone else approves them with a passkey.')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Propose a change' })).toBeNull();

    await waitFor(() => expect(group('client_category')).not.toBeNull());
    expect(item('service_type', 'advice')).toHaveTextContent('Advice In our scope Removed when approved');
    expect(item('client_category', 'retail')).toHaveTextContent('Retail Not in our scope Added when approved');
    expect(item('client_category', 'professional')).toHaveTextContent('Professional Not in our scope');
    expect(item('service_type', 'custody')).not.toHaveTextContent('when approved');

    const disclosure = within(banner).getByRole('button', { name: 'See the preview' });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(disclosure);
    expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    const shown = document.querySelector<HTMLElement>('[data-pending-preview]')!;
    expect(within(shown).getByText('Hides')).toBeVisible();
    expect(within(shown).getByText('2 obligations')).toBeVisible();
    expect(disclosure).toHaveAttribute('aria-controls', shown.id);

    fireEvent.click(within(banner).getByRole('button', { name: 'Withdraw' }));
    await waitFor(() => expect(document.activeElement).toBe(statusLine()));
    expect(statusLine()).toHaveTextContent('Withdrawn.');
    expect(sent.find((s) => s.path === `${REQUESTS}/r1/withdraw`)).toBeDefined();
    await waitFor(() => expect(document.querySelector('[data-pending-request]')).toBeNull());
  });

  it('renders a failed withdrawal under the banner, never inside it', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    serve(me, waiting(SARA), () => ({ status: 409, data: { code: 'invalid_transition', detail: 'This request was already decided.' } }));
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw' }));
    const alert = await screen.findByText('This request was already decided.');
    expect(alert.closest('[data-pending-request]')).toBeNull();
    expect(statusLine()).toBeEmptyDOMElement();
  });

  it('gives a request-only member who did not ask for it the banner and no buttons', async () => {
    const me = meOf(ERIK, ['footprint.request']);
    serve(me, waiting(SARA));
    open(me);
    const banner = await findBanner();
    expect(await within(banner).findByText(/^Requested by Sara Lindqvist, .+\. Hides 2 obligations and reveals 1 obligation\.$/)).toBeVisible();
    expect(within(banner).getByText('No other change can be proposed until this one is decided.')).toBeVisible();
    expect(within(banner).getAllByRole('button').map((button) => button.textContent)).toEqual(['See the preview']);
  });
});

describe('FootprintScreen: deciding', () => {
  it('approves in a dialog that states the change, warns what it hides and narrows, and then focuses the status line', async () => {
    const me = meOf(MARIA, ['footprint.approve']);
    const { sent } = serve(me, waiting(SARA), (s, server) => {
      if (s.path === `${REQUESTS}/r1/approve`) {
        server.pending = null;
        return { status: 200, data: { ...waiting(), status: 'approved', decidedBy: MARIA } };
      }
      return { status: 500 };
    });
    open(me);

    const banner = await findBanner();
    expect(await within(banner).findByText(/^Requested by Sara Lindqvist, .+\. Hides 2 obligations and reveals 1 obligation\.$/)).toBeVisible();
    expect(within(banner).queryByText('No other change can be proposed until this one is decided.')).toBeNull();
    expect(within(banner).queryByRole('button', { name: 'Withdraw' })).toBeNull();
    expect(within(banner).getAllByRole('button').map((button) => button.textContent)).toEqual(['See the preview', 'Reject', 'Approve']);

    fireEvent.click(within(banner).getByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve "Add Retail, remove Advice"?' });
    expect(dialog).toHaveAccessibleDescription('Hides 2 obligations and reveals 1 obligation.');
    const warning = dialog.querySelector<HTMLElement>('[data-notice="warn"]')!;
    expect(within(warning).getByText('What this hides leaves the feed, the inventory, the roadmap and the briefing for every member.')).toBeVisible();
    expect(within(warning).getByText('Client category will start to filter: records tagged only with other options in it are hidden from every member.')).toBeVisible();
    expectWarnNoticesInTextColour();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve with passkey' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(statusLine()));
    expect(statusLine()).toHaveTextContent('Approved. The regulatory scope has changed.');
    expect(sent.find((s) => s.path === `${REQUESTS}/r1/approve`)).toBeDefined();
  });

  it('shows the four-eyes refusal in the dialog, above its buttons', async () => {
    const me = meOf(MARIA, ['footprint.approve']);
    serve(me, waiting(SARA), () => ({ status: 409, data: { code: 'four_eyes_violation', detail: 'The requester cannot approve.' } }));
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve with passkey' }));
    const refusal = await within(dialog).findByRole('alert');
    expect(refusal).toHaveTextContent('You requested this change, so someone else has to approve it.');
    expect(within(dialog).getByRole('button', { name: 'Approve with passkey' })).toBeDisabled();
    expect(statusLine()).toBeEmptyDOMElement();
  });

  it('refuses a blank rejection by focusing the reason, then rejects with one and focuses the status line', async () => {
    const me = meOf(MARIA, ['footprint.approve']);
    const { sent } = serve(me, waiting(SARA), (s, server) => {
      if (s.path === `${REQUESTS}/r1/reject`) {
        server.pending = null;
        return { status: 200, data: { ...waiting(), status: 'rejected', decidedBy: MARIA, decisionNote: (s.body as { note: string }).note } };
      }
      return { status: 500 };
    });
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog', { name: 'Reject this change' });
    const reason = within(dialog).getByLabelText('Reason');
    expect(reason).toHaveAttribute('aria-required', 'true');
    expect(reason).toHaveAccessibleDescription('Shown to the requester and kept in the audit log.');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Give a reason.');
    expect(reason).toHaveAttribute('aria-invalid', 'true');
    expect(reason).toHaveAccessibleDescription('Shown to the requester and kept in the audit log. Give a reason.');
    expect(document.activeElement).toBe(reason);
    expect(sent.some((s) => s.path.endsWith('/reject'))).toBe(false);

    fireEvent.change(reason, { target: { value: 'We still advise in private banking' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(document.activeElement).toBe(statusLine()));
    expect(statusLine()).toHaveTextContent('Rejected.');
    expect(sent.find((s) => s.path === `${REQUESTS}/r1/reject`)?.body).toEqual({ note: 'We still advise in private banking' });
  });
});

describe('FootprintScreen: markets we watch', () => {
  const panel = () => document.querySelector<HTMLElement>('[data-markets]')!;
  const market = (key: string) => panel().querySelector<HTMLElement>(`[data-market="${key}"]`)!;

  /** The watch routes as the server answers them: a repeat is 409, an unwatched market 404. */
  const watching: Mutation = (s, server) => {
    const key = (s.body as { jurisdiction: string }).jurisdiction;
    const row = server.markets.find((m) => m.jurisdiction.key === key)!;
    const adding = s.path === WATCHING;
    if (adding && row.level === 'watching') return { status: 409, data: { code: 'already_watching', detail: `'${key}' is already watched.` } };
    if (!adding && row.level !== 'watching') return { status: 404, data: { code: 'not_found', detail: `'${key}' is not watched.` } };
    const next = { ...row, level: adding ? ('watching' as const) : ('not_followed' as const) };
    server.markets = server.markets.map((m) => (m.jurisdiction.key === key ? next : m));
    return { status: 200, data: next };
  };

  it('lists every country with its level for someone who can watch: Operating as text, a pressed Watching toggle, and the two notes', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { sent, server } = serve(me, null, watching);
    open(me);

    expect(await screen.findByRole('heading', { level: 2, name: 'Markets we watch' })).toBeVisible();
    expect(within(panel()).getByText('The jurisdictions in our regulatory scope are the markets we operate in. Watching a market hides nothing.')).toBeVisible();
    expect([...panel().querySelectorAll('[data-market]')].map((row) => row.getAttribute('data-market'))).toEqual(['se', 'dk', 'no', 'fi']);
    expect(market('se')).toHaveTextContent('SwedenOperating');
    expect(within(market('se')).queryByRole('button')).toBeNull();
    expect(within(market('dk')).getByRole('button', { name: 'Watching Denmark' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(market('fi')).getByRole('button', { name: 'Watching Finland' })).toHaveAttribute('aria-pressed', 'false');
    expect(await within(panel()).findByText('European Union rules reach Sweden, Denmark, Norway and Finland, so they show wherever those markets do.')).toBeVisible();
    expect(within(panel()).getByRole('heading', { level: 3, name: 'Also included' })).toBeVisible();
    expect(within(panel()).getByRole('heading', { level: 3, name: 'Everywhere else' })).toBeVisible();
    expect(within(panel()).getByText('Our research sweeps every source in the library for every market, whatever you choose here.')).toBeVisible();
    expect(within(panel()).queryByRole('status')).toBeNull();

    // Watching saves at once, with the key in the body and never in the path.
    fireEvent.click(within(market('fi')).getByRole('button', { name: 'Watching Finland' }));
    await waitFor(() => expect(within(market('fi')).getByRole('button', { name: 'Watching Finland' })).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(within(market('dk')).getByRole('button', { name: 'Watching Denmark' }));
    await waitFor(() => expect(within(market('dk')).getByRole('button', { name: 'Watching Denmark' })).toHaveAttribute('aria-pressed', 'false'));
    expect(sent.filter((s) => s.method === 'post').map((s) => [s.path, s.params, s.body])).toEqual([
      [WATCHING, null, { jurisdiction: 'fi' }],
      [`${WATCHING}/remove`, null, { jurisdiction: 'dk' }],
    ]);
    expect(server.markets.map((m) => m.level)).toEqual(['operating', 'not_followed', 'watching', 'watching']);
    expect(statusLine()).toBeEmptyDOMElement();
  });

  it('reads every level in words for someone who can only approve, under a notice of its own, with nothing to press', async () => {
    const me = meOf(MARIA, ['footprint.approve']);
    serve(me);
    open(me);
    await screen.findByRole('heading', { level: 2, name: 'Markets we watch' });
    expect(within(panel()).getByText('You can see the regulatory scope. Changing it needs footprint request; ask a compliance officer or an administrator.')).toBeVisible();
    expect(within(panel()).queryAllByRole('button')).toHaveLength(0);
    expect(['se', 'dk', 'no', 'fi'].map((key) => market(key).textContent)).toEqual(['SwedenOperating', 'DenmarkWatching', 'NorwayWatching', 'FinlandNot watched']);
  });

  it('says a market was not saved when the server refuses, and keeps the level the server holds', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const { server } = serve(me, null, watching);
    open(me);
    const norway = await waitFor(() => within(market('no')).getByRole('button', { name: 'Watching Norway' }));
    // Someone else stopped watching Norway after this page read it: the unwatch answers 404.
    server.markets = server.markets.map((m) => (m.jurisdiction.key === 'no' ? { ...m, level: 'not_followed' as const } : m));
    fireEvent.click(norway);

    const refusal = await within(panel()).findByRole('alert');
    expect(refusal).toHaveTextContent('Norway was not saved. Try again.');
    await waitFor(() => expect(within(market('no')).getByRole('button', { name: 'Watching Norway' })).toHaveAttribute('aria-pressed', 'false'));
    expect(statusLine()).toBeEmptyDOMElement();

    // A repeated watch is the same state: 409, and the toggle shows what the server holds.
    server.markets = server.markets.map((m) => (m.jurisdiction.key === 'no' ? { ...m, level: 'watching' as const } : m));
    fireEvent.click(within(market('no')).getByRole('button', { name: 'Watching Norway' }));
    await waitFor(() => expect(within(market('no')).getByRole('button', { name: 'Watching Norway' })).toHaveAttribute('aria-pressed', 'true'));
    expect(within(panel()).getByRole('alert')).toHaveTextContent('Norway was not saved. Try again.');
  });
});

describe('FootprintScreen: the history, one page at a time', () => {
  it('shows the first page and "Show more" while the total says there are more, reading on from where it ended', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    const decided = (i: number) => ({ ...HISTORY.items[0], id: `h${i}`, decisionNote: `Reason ${i}` });
    const sent = installAdapter((s) => {
      if (s.path === ME) return { status: 200, data: me };
      if (s.path === FOOTPRINT) return { status: 200, data: scope() };
      if (s.path === TERMS) return { status: 200, data: TAXONOMY };
      if (s.path === JURISDICTIONS) return { status: 200, data: REFERENCE };
      const { limit, offset } = s.params as { limit: number; offset: number };
      const total = limit + 1;
      return { status: 200, data: { items: Array.from({ length: Math.min(limit, total - offset) }, (_, i) => decided(offset + i)), total } };
    });
    open(me);
    const history = await waitFor(() => {
      const found = document.querySelector<HTMLElement>('[data-footprint-history]');
      if (found === null) throw new Error('no history yet');
      return found;
    });
    const more = await within(history).findByRole('button', { name: 'Show more' });
    const first = history.querySelectorAll('[data-history-entry]').length;
    expect(first).toBeGreaterThan(0);

    fireEvent.click(more);
    await waitFor(() => expect(history.querySelectorAll('[data-history-entry]')).toHaveLength(first + 1));
    expect(within(history).queryByRole('button', { name: 'Show more' })).toBeNull();
    const pages = sent.filter((s) => s.path === REQUESTS).map((s) => s.params as { limit: number; offset: number });
    expect(pages).toEqual([
      { limit: first, offset: 0 },
      { limit: first, offset: first },
    ]);
  });
});

describe('FootprintScreen: loading, error and denied', () => {
  it('shows a skeleton while loading', () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    serve(me);
    open(me);
    expect(document.querySelector('[data-loading-state]')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('heading', { level: 1, name: 'Regulatory scope' })).toBeVisible();
  });

  it('says it could not load, and Try again reads it again', async () => {
    const me = meOf(SARA, REQUEST_AND_APPROVE);
    let fail = true;
    installAdapter((s) => {
      if (s.path === ME) return { status: 200, data: me };
      if (s.path === FOOTPRINT) return fail ? { status: 500, data: { code: 'server_error', detail: '' } } : { status: 200, data: scope() };
      if (s.path === TERMS) return { status: 200, data: TAXONOMY };
      return { status: 200, data: HISTORY };
    });
    open(me);
    expect(await screen.findByRole('heading', { name: 'Could not load the regulatory scope' })).toBeVisible();
    fail = false;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(group('service_type')).not.toBeNull());
  });

  it('gives a member without either permission the restricted page', () => {
    const me = meOf(ERIK, ['watch.read', 'audit.read']);
    serve(me);
    render(
      shell(
        <AdminGate id="admin-footprint">
          <FootprintScreen />
        </AdminGate>,
        me.permissions,
      ).node,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'This page is not available to you' })).toBeVisible();
    expect(screen.getByText('Needs footprint request')).toBeVisible();
    expect(document.querySelector('[data-dimension]')).toBeNull();
  });
});
