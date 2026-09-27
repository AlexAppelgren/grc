import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ObligationGapsPanel } from '@/components/inventory/ObligationGapsPanel';
import type { RegisterGap } from '@/features/register/types';
import type { Locale } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

import { GapsScreen } from './GapsScreen';

// The gaps screen, the gap record and the obligation's gaps panel
// (design/screens/tenant-gaps.html; REG-03, REG-S5, REG-S6). The server is
// scripted per call; what the screen sends is read back. The journeys prove
// the contract against the real stack.

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/gaps',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };
const MARIA = { id: 'u-maria', name: 'Maria Svensson' };
const ENTITY = 'ou-bank';

function me(user: { id: string; name: string }) {
  return {
    user: { ...user, email: 'someone@bank.example', locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank', timezone: 'Europe/Stockholm' },
    roles: [],
    permissions: [],
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 1,
    stepUpValidUntil: null,
  };
}

function gap(overrides: Partial<RegisterGap> = {}): RegisterGap {
  return {
    id: 'g-1',
    obligationId: 'ob-1',
    orgUnitId: ENTITY,
    unitId: null,
    title: 'Currency exchange cost is missing from the ex ante view',
    description: 'The ex ante view leaves out the exchange cost.',
    severity: { key: 'high', kind: 'high', label: 'High' },
    source: { key: 'assessment', kind: null, label: 'Self-assessment' },
    status: { key: 'open', kind: 'open', label: 'Open' },
    owner: SARA,
    ownerTeam: null,
    targetDate: '2099-11-30',
    remediation: 'Add the cost to the view.',
    identifiedAt: '2026-09-12T08:00:00Z',
    identifiedBy: SARA,
    riskAcceptance: null,
    version: 3,
    ...overrides,
  };
}

const waiting = { reason: { key: 'compensating_control', kind: null, label: 'A compensating control covers it' }, note: null, requestedBy: SARA, requestedAt: '2026-09-22T09:00:00Z', approvedBy: null, approvedAt: null };

const VOCAB: Record<string, { key: string; kind: string | null; label: string }[]> = {
  gap_status: [
    { key: 'open', kind: 'open', label: 'Open' },
    { key: 'remediating', kind: 'remediating', label: 'Remediating' },
    { key: 'risk_accepted', kind: 'risk_accepted', label: 'Risk accepted' },
    { key: 'closed', kind: 'closed', label: 'Closed' },
  ],
  risk_rating: [
    { key: 'high', kind: 'high', label: 'High' },
    { key: 'low', kind: 'low', label: 'Low' },
  ],
  gap_source: [
    { key: 'assessment', kind: null, label: 'Self-assessment' },
    { key: 'audit', kind: null, label: 'Internal audit' },
  ],
  team: [{ key: 'retail', kind: null, label: 'Retail compliance' }],
  risk_acceptance_reason: [
    { key: 'management', kind: null, label: 'Accepted by management' },
    { key: 'compensating_control', kind: null, label: 'A compensating control covers it' },
  ],
};

const ref = (key: string) => ({ key, kind: null, label: key });
const obligation = {
  id: 'ob-1',
  stableKey: 'obl-costs-charges',
  refLabel: 'Costs and charges',
  title: { text: 'Disclose all costs and charges', language: 'en', isOriginal: true, isMachine: false },
  instrument: { key: 'mifid-ii', shortName: 'MiFID II', officialRef: '2014/65/EU', name: null, implementsNote: '' },
  regime: ref('securities'),
  bindingLevel: ref('eu_directive'),
  binding: true,
  dutyType: ref('disclosure'),
  productScope: '',
  triggerFrequency: '',
  retention: '',
  sanctionExposure: '',
  tags: [],
  scope: [],
  inFootprint: true,
  outsideReason: [],
  summary: null,
  translations: [],
  version: null,
  versions: [],
  related: [],
  provenance: { sourceLabel: '', sourceUrl: '', lastVerifiedAt: null, verifiedBy: null, verifiedOrigin: '', createdAt: '2026-01-01T00:00:00Z', createdModel: '', createdOrigin: 'user', confirmedByAgent: null, proposedByAgent: null },
};

function serve(options: { who?: { id: string; name: string }; gaps?: RegisterGap[]; write?: (sent: Sent) => Answer; gapsAnswer?: Answer } = {}): Sent[] {
  const who = options.who ?? SARA;
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === '/api/v1/me') return { status: 200, data: me(who) };
    if (sent.method !== 'get') return options.write?.(sent) ?? { status: 200, data: gap() };
    if (sent.path === '/api/v1/gaps' || sent.path === '/api/v1/obligations/ob-1/gaps') {
      if (options.gapsAnswer !== undefined) return options.gapsAnswer;
      const items = options.gaps ?? [gap()];
      return { status: 200, data: { items, total: items.length } };
    }
    if (sent.path === '/api/v1/obligations/ob-1') return { status: 200, data: obligation };
    const list = /^\/api\/v1\/vocab\/(\w+)$/.exec(sent.path)?.[1];
    if (list !== undefined && VOCAB[list] !== undefined) return { status: 200, data: { items: VOCAB[list], total: VOCAB[list].length } };
    return { status: 404, data: { code: 'not_found', detail: 'Not in this test.' } };
  });
}

function renderIn(node: ReactNode, permissions: string[], locale: Locale = 'en') {
  const { wrapper: Query } = queryWrapper();
  return render(
    <Query>
      <LocaleProvider locale={locale}>
        <PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

const EDITOR = ['register.read', 'gaps.edit'];
const OFFICER = ['register.read', 'gaps.edit', 'risk.accept.approve'];
const APPROVER = ['register.read', 'risk.accept.approve'];

async function openRecord(): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole('button', { name: /Currency exchange cost/ }));
  return (await waitFor(() => {
    const record = document.querySelector('[data-gap-record]');
    expect(record).not.toBeNull();
    return record;
  })) as HTMLElement;
}

function wayOut(): HTMLElement {
  return document.querySelector('[data-gap-way-out]') as HTMLElement;
}

describe('the gaps list', () => {
  beforeEach(() => {
    resetApiForTests();
    nav.search = '';
    nav.replace.mockReset();
  });

  it('lists each gap with its pills, obligation, entity, owner and target, and opens its record', async () => {
    serve();
    renderIn(<GapsScreen />, EDITOR);
    const row = (await screen.findByRole('button', { name: /Currency exchange cost/ })).closest('[data-gap]') as HTMLElement;
    expect(within(row).getByText('Open')).toHaveAttribute('data-pill', 'negative');
    expect(within(row).getByText('High')).toHaveAttribute('data-pill', 'negative');
    expect(within(row).getByText('Self-assessment')).toHaveAttribute('data-pill', 'information');
    expect(await within(row).findByText('Disclose all costs and charges')).toBeInTheDocument();
    expect(within(row).getByText('Sara Lindqvist')).toBeInTheDocument();
    expect(within(row).getByText(/^Target 30 Nov 2099, in /)).toBeInTheDocument();
    expect(screen.getByText('1 gap')).toBeInTheDocument();

    const record = await openRecord();
    expect(within(record).getByRole('heading', { name: 'What is missing' })).toBeInTheDocument();
    expect(within(record).getByText('Add the cost to the view.')).toBeInTheDocument();
    expect(within(record).getByRole('link', { name: 'Disclose all costs and charges' })).toHaveAttribute('href', '/inventory/obligations/ob-1');
    expect(within(wayOut()).getByRole('button', { name: 'Start remediation' })).toBeInTheDocument();
  });

  it('keeps each filter as a key in the address and reads it back into the request', async () => {
    nav.search = 'status=remediating&owner=me&targetTo=2026-12-31';
    const sent = serve({ gaps: [] });
    renderIn(<GapsScreen />, EDITOR);
    expect(await screen.findByText('No gaps match these filters')).toBeInTheDocument();
    const list = sent.find((s) => s.path === '/api/v1/gaps');
    expect(list?.params).toMatchObject({ status: 'remediating', owner: SARA.id, targetTo: '2026-12-31', limit: 20, offset: 0 });

    fireEvent.change(document.querySelector('[data-gap-filter="severity"]') as HTMLElement, { target: { value: 'high' } });
    expect(nav.replace).toHaveBeenCalledWith('/gaps?status=remediating&owner=me&targetTo=2026-12-31&severity=high');
    fireEvent.click(screen.getAllByRole('button', { name: 'Clear filters' })[0] as HTMLElement);
    expect(nav.replace).toHaveBeenLastCalledWith('/gaps');
  });

  it('says so when nothing is recorded, and offers a retry when the list fails', async () => {
    serve({ gaps: [] });
    const { unmount } = renderIn(<GapsScreen />, EDITOR);
    expect(await screen.findByText('No gaps recorded')).toBeInTheDocument();
    unmount();

    resetApiForTests();
    serve({ gapsAnswer: { status: 500, data: { code: 'server_error', detail: 'Down.' } } });
    renderIn(<GapsScreen />, EDITOR);
    expect(await screen.findByText('Gaps could not be loaded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('pages through more than twenty gaps', async () => {
    installAdapter((sent) => {
      if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
      if (sent.path === '/api/v1/me') return { status: 200, data: me(SARA) };
      if (sent.path === '/api/v1/gaps') return { status: 200, data: { items: [gap()], total: 45 } };
      return { status: 200, data: { items: [], total: 0, entities: [] } };
    });
    renderIn(<GapsScreen />, EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
    expect(nav.replace).toHaveBeenCalledWith('/gaps?page=1');
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
  });
});

describe('the way out', () => {
  beforeEach(() => {
    resetApiForTests();
    nav.search = '';
  });

  it('starts remediation by the key of the remediating row, with the version last read', async () => {
    const sent = serve({ write: () => ({ status: 200, data: gap({ status: VOCAB.gap_status?.[1] as RegisterGap['status'] }) }) });
    renderIn(<GapsScreen />, EDITOR);
    await openRecord();
    const start = within(wayOut()).getByRole('button', { name: 'Start remediation' });
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    expect(await screen.findByText('Remediation started.')).toBeInTheDocument();
    expect(sent.find((s) => s.method === 'patch')).toMatchObject({ path: '/api/v1/gaps/g-1', body: { status: 'remediating' } });
  });

  it('closes a gap under way after a confirmation, and answers a stale write in place with Reload', async () => {
    serve({ gaps: [gap({ status: { key: 'remediating', kind: 'remediating', label: 'Remediating' } })], write: () => ({ status: 409, data: { code: 'stale_write', detail: 'Changed.' } }) });
    renderIn(<GapsScreen />, EDITOR);
    await openRecord();
    const close = within(wayOut()).getByRole('button', { name: 'Close gap' });
    await waitFor(() => expect(close).toBeEnabled());
    fireEvent.click(close);
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Close this gap?' })).getByRole('button', { name: 'Close gap' }));
    expect(await screen.findByText('Someone changed this gap while you were editing. Reload to see their version, then make your change again.')).toBeInTheDocument();
    expect(within(wayOut()).getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it.each(['en', 'sv'] as const)('asks to accept the risk with a reason key, showing the labels (%s)', async (locale) => {
    const sent = serve({ write: () => ({ status: 200, data: gap({ riskAcceptance: waiting }) }) });
    renderIn(<GapsScreen />, EDITOR, locale);
    fireEvent.click(await screen.findByRole('button', { name: /Currency exchange cost/ }));
    fireEvent.click(await screen.findByRole('button', { name: locale === 'en' ? 'Accept the risk' : 'Acceptera risken' }));
    const form = await waitFor(() => document.querySelector('[data-accept-risk-form]') as HTMLElement);
    fireEvent.click(within(form).getByRole('button', { name: locale === 'en' ? 'Ask for approval' : 'Begär godkännande' }));
    expect(within(form).getByText(locale === 'en' ? 'Choose a reason.' : 'Välj ett skäl.')).toBeInTheDocument();

    const picker = within(form).getByRole('combobox');
    expect(await within(picker).findByRole('option', { name: 'A compensating control covers it' })).toBeInTheDocument();
    fireEvent.change(picker, { target: { value: 'compensating_control' } });
    fireEvent.click(within(form).getByRole('button', { name: locale === 'en' ? 'Ask for approval' : 'Begär godkännande' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'post' && s.path.includes('/gaps'))).toMatchObject({ path: '/api/v1/gaps/g-1/accept-risk', body: { reason: 'compensating_control' } }));
  });

  it('shows the requester the waiting acceptance and no Approve', async () => {
    serve({ gaps: [gap({ riskAcceptance: waiting })] });
    renderIn(<GapsScreen />, OFFICER);
    expect(await screen.findByText('Risk acceptance waiting for approval')).toBeInTheDocument();
    await openRecord();
    const panel = wayOut();
    expect(within(panel).getByText('Waiting for approval')).toHaveAttribute('data-pill', 'warning');
    expect(within(panel).getByText('You asked for this, so someone else has to approve it.')).toBeInTheDocument();
    expect(within(panel).getByText('A compensating control covers it')).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Approve with passkey' })).toBeNull();
  });

  it('lets a second person approve, and renders a four-eyes refusal from its code', async () => {
    const sent = serve({ who: MARIA, gaps: [gap({ riskAcceptance: waiting })], write: () => ({ status: 409, data: { code: 'four_eyes_violation', detail: 'Server words.' } }) });
    renderIn(<GapsScreen />, APPROVER);
    await openRecord();
    expect(within(wayOut()).getByText(/^Sara Lindqvist asks to accept the risk, 22 Sept? 2026\.$/)).toBeInTheDocument();
    fireEvent.click(within(wayOut()).getByRole('button', { name: 'Approve with passkey' }));
    const dialog = await screen.findByRole('dialog', { name: 'Accept the risk of "Currency exchange cost is missing from the ex ante view"?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve with passkey' }));
    expect(await within(wayOut()).findByText('You asked for this, so someone else has to approve it.')).toHaveAttribute('data-problem-code', 'four_eyes_violation');
    expect(sent.find((s) => s.method === 'post' && s.path.includes('/gaps'))?.path).toBe('/api/v1/gaps/g-1/accept-risk/approve');
  });

  it('reads Risk accepted in information with both names, and reopens it', async () => {
    const accepted = gap({ status: { key: 'risk_accepted', kind: 'risk_accepted', label: 'Risk accepted' }, riskAcceptance: { ...waiting, approvedBy: MARIA, approvedAt: '2026-09-23T09:00:00Z' } });
    const sent = serve({ gaps: [accepted], write: () => ({ status: 200, data: gap() }) });
    renderIn(<GapsScreen />, EDITOR);
    await openRecord();
    expect(document.querySelector('[data-gap] [data-pill]')).toHaveTextContent('Risk accepted');
    expect(document.querySelector('[data-gap] [data-pill]')).toHaveAttribute('data-pill', 'information');
    expect(within(wayOut()).getByText(/^Risk accepted by Maria Svensson on 23 Sept? 2026, asked by Sara Lindqvist\.$/)).toBeInTheDocument();
    fireEvent.click(within(wayOut()).getByRole('button', { name: 'Reopen' }));
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Reopen this gap?' })).getByRole('button', { name: 'Reopen' }));
    expect(await screen.findByText('Gap reopened.')).toBeInTheDocument();
    expect(sent.find((s) => s.method === 'post' && s.path.includes('/gaps'))?.path).toBe('/api/v1/gaps/g-1/reopen');
  });

  it('tells a reader who owns the work, with no buttons', async () => {
    serve({ gaps: [gap({ status: { key: 'remediating', kind: 'remediating', label: 'Remediating' }, owner: null, ownerTeam: { key: 'retail', kind: null, label: 'Retail compliance' } })] });
    renderIn(<GapsScreen />, ['register.read']);
    await openRecord();
    expect(within(wayOut()).getByText('Remediation is under way. Retail compliance owns it.')).toBeInTheDocument();
    expect(within(wayOut()).queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });
});

describe('the gaps panel on the obligation', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('asks nothing of a member whose roles do not read the register', () => {
    const sent = serve();
    const { container } = renderIn(<ObligationGapsPanel obligationId="ob-1" />, ['library.read']);
    expect(container).toBeEmptyDOMElement();
    expect(sent.filter((s) => s.path.includes('/gaps'))).toHaveLength(0);
  });

  it('says when no gap is recorded, and reads the record of one in a legal entity', async () => {
    serve({ gaps: [] });
    const { unmount } = renderIn(<ObligationGapsPanel obligationId="ob-1" />, EDITOR);
    expect(await screen.findByText('No gaps recorded.')).toBeInTheDocument();
    unmount();

    resetApiForTests();
    serve();
    renderIn(<ObligationGapsPanel obligationId="ob-1" />, ['register.read']);
    const record = await openRecord();
    expect(within(record).getByText('One legal entity')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Record a gap' })).toBeNull();
  });

  it('records a gap with keys from the bank lists, a team as owner, and refuses a past date', async () => {
    const sent = serve({ gaps: [], write: () => ({ status: 201, data: gap({ id: 'g-new' }) }) });
    renderIn(<ObligationGapsPanel obligationId="ob-1" />, EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Record a gap' }));
    const form = await waitFor(() => document.querySelector('[data-gap-form]') as HTMLElement);
    await within(form).findByRole('option', { name: 'Retail compliance, a team' });
    await within(form).findByRole('option', { name: 'Internal audit' });
    await within(form).findByRole('option', { name: 'High' });
    fireEvent.click(within(form).getByRole('button', { name: 'Record gap' }));
    expect(within(form).getByText('Give the gap a title.')).toBeInTheDocument();

    fireEvent.change(within(form).getByLabelText('Title'), { target: { value: 'Exchange cost missing' } });
    fireEvent.change(within(form).getByLabelText('Target date'), { target: { value: '2001-01-01' } });
    fireEvent.change(within(form).getByLabelText('Found through'), { target: { value: 'audit' } });
    fireEvent.change(within(form).getByLabelText('Owner'), { target: { value: 'team:retail' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Record gap' }));
    expect(within(form).getByText('Pick a date from today on.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'post' && s.path.includes('/gaps'))).toHaveLength(0);

    fireEvent.change(within(form).getByLabelText('Target date'), { target: { value: '2099-12-31' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Record gap' }));
    await waitFor(() =>
      expect(sent.find((s) => s.method === 'post' && s.path.includes('/gaps'))).toMatchObject({
        path: '/api/v1/obligations/ob-1/gaps',
        body: { title: 'Exchange cost missing', severity: 'high', source: 'audit', ownerTeam: 'retail', targetDate: '2099-12-31', description: null, remediation: null },
      }),
    );
  });

  it('edits a gap and sends the owner only when it changed', async () => {
    const sent = serve({ write: () => ({ status: 200, data: gap() }) });
    renderIn(<ObligationGapsPanel obligationId="ob-1" />, EDITOR);
    await openRecord();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const form = await waitFor(() => document.querySelector('[data-gap-form]') as HTMLElement);
    expect(within(form).queryByLabelText('Found through')).toBeNull();
    fireEvent.change(within(form).getByLabelText('Remediation plan'), { target: { value: 'A new plan.' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Gap saved.')).toBeInTheDocument();
    const patch = sent.find((s) => s.method === 'patch');
    expect(patch).toMatchObject({ path: '/api/v1/gaps/g-1', body: { remediation: 'A new plan.', severity: 'high', targetDate: '2099-11-30' } });
    expect(patch?.body).not.toHaveProperty('ownerId');
  });
});
