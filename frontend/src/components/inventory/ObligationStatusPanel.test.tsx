import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { RegisterEntityStatus, RegisterEntry } from '@/features/register/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { changesOf, ObligationStatusPanel } from './ObligationStatusPanel';

// "Where we stand" and "How we handle it" (design/screens/tenant-obligation.html;
// REG-02, D-42): the worst-of header naming its entity, a row per entity the
// obligation applies to, the owner as a person or a team, nothing asked where it
// does not apply, edits behind register.edit sending only what changed, and the
// stale write read from its code. Every date is fixed.

const ME = { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false };
const COMPLIANT = { key: 'compliant', kind: 'compliant', label: 'Compliant' };
const PARTLY = { key: 'partly_compliant', kind: 'partly', label: 'Partly compliant' };
const NOT_ASSESSED = { key: 'not_assessed', kind: 'not_assessed', label: 'Not assessed' };
const HIGH = { key: 'high', kind: null, label: 'High' };
const RETAIL = { key: 'retail_compliance', kind: null, label: 'Retail compliance' };
const ANNA = { id: 'p-anna', name: 'Anna Nilsson' };
const SARA = { id: 'p-sara', name: 'Sara Lindqvist' };

function entity(id: string, name: string, patch: Partial<RegisterEntityStatus> = {}): RegisterEntityStatus {
  return {
    orgUnitId: id,
    orgUnitName: name,
    applicability: 'applies',
    applicabilityReason: 'Advises on its own products.',
    applicabilityDecidedAt: '2026-09-18T08:30:00Z',
    applicabilityDecidedBy: SARA,
    complianceStatus: COMPLIANT,
    statusNote: null,
    riskRating: null,
    owner: null,
    ownerTeam: null,
    process: null,
    system: null,
    evidenceLocation: null,
    nextReviewDate: null,
    version: 1,
    ...patch,
  };
}

function entry(patch: Partial<RegisterEntry> = {}): RegisterEntry {
  return {
    obligationId: 'ob-1',
    applicability: 'applies',
    applicabilityReason: 'Both entities advise.',
    applicabilityDecidedAt: '2026-09-18T08:30:00Z',
    applicabilityDecidedBy: SARA,
    complianceStatus: COMPLIANT,
    statusNote: null,
    riskRating: null,
    firstLineOwner: null,
    complianceContact: null,
    ownerTeam: null,
    process: null,
    system: null,
    evidenceLocation: null,
    nextReviewDate: null,
    entities: [],
    version: 5,
    updatedAt: '2026-09-18T08:30:00Z',
    ...patch,
  };
}

const TWO = entry({
  complianceStatus: PARTLY,
  entities: [
    entity('e-bank', 'Example Bank AB', { statusNote: 'Criteria adopted.', owner: ANNA, nextReviewDate: '2027-09-01' }),
    entity('e-finans', 'Example Finans AB', { complianceStatus: PARTLY, riskRating: HIGH, ownerTeam: RETAIL, version: 4 }),
  ],
});

function serve(read: RegisterEntry | number, write: (sent: Sent) => { status: number; data?: unknown } = () => ({ status: 200, data: {} })): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: ME };
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: [ANNA, SARA] };
    if (sent.path === '/api/v1/vocab/compliance_status') return { status: 200, data: { items: [COMPLIANT, PARTLY, NOT_ASSESSED], total: 3 } };
    if (sent.path === '/api/v1/vocab/risk_rating') return { status: 200, data: { items: [HIGH], total: 1 } };
    if (sent.path === '/api/v1/vocab/team') return { status: 200, data: { items: [RETAIL], total: 1 } };
    if (sent.method === 'patch') return write(sent);
    if (typeof read === 'number') return { status: read, data: { detail: 'no', code: 'server_error' } };
    return { status: 200, data: read };
  });
}

function renderPanel(permissions: string[] = ['register.read', 'register.edit']) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <ObligationStatusPanel obligationId="ob-1" />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

const patches = (sent: Sent[]) => sent.filter((call) => call.method === 'patch').map((call) => ({ path: call.path, body: call.body }));
const rowOf = (name: string) => screen.getByText(name).closest('[data-status-row]') as HTMLElement;

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('session-token');
});

describe('changesOf', () => {
  const blank = { status: 'compliant', rationale: '', note: 'Old', risk: '', owner: '', team: '', contact: '', process: '', system: '', evidence: '', review: '' };

  it('sends nothing when nothing moved', () => {
    expect(changesOf(blank, blank, { kind: 'whole' })).toEqual({});
  });

  it('sends the rationale only with a status change, clears an emptied text and names a team or a person by field', () => {
    expect(changesOf(blank, { ...blank, rationale: 'Sampled.' }, { kind: 'whole' })).toEqual({});
    expect(changesOf(blank, { ...blank, status: 'gap', rationale: ' Sampled. ', note: '' }, { kind: 'whole' })).toEqual({
      complianceStatus: 'gap',
      rationale: 'Sampled.',
      statusNote: '',
    });
    expect(changesOf(blank, { ...blank, owner: 'person:p-anna' }, { kind: 'whole' })).toEqual({ firstLineOwnerId: 'p-anna' });
    const finans = { kind: 'entity' as const, entity: entity('e-finans', 'Example Finans AB') };
    expect(changesOf(blank, { ...blank, owner: 'person:p-anna' }, finans)).toEqual({ ownerId: 'p-anna' });
    expect(changesOf(blank, { ...blank, owner: 'team:retail_compliance' }, finans)).toEqual({ ownerTeam: 'retail_compliance' });
  });

  it('keeps how it is handled apart from where it stands', () => {
    const moved = { ...blank, status: 'gap', process: 'Research budget' };
    expect(changesOf(blank, moved, { kind: 'handle' })).toEqual({ process: 'Research budget' });
    expect(changesOf(blank, moved, { kind: 'whole' })).toEqual({ complianceStatus: 'gap' });
  });
});

describe('ObligationStatusPanel', () => {
  it('shows the worst of the entities on the header, naming it, and a row per entity with its own facts', async () => {
    serve(TWO);
    renderPanel(['register.read']);
    const header = (await screen.findByText('at Example Finans AB, the weakest legal entity')).closest('[data-status-header]') as HTMLElement;
    expect(within(header).getByText('Partly compliant')).toBeInTheDocument();
    const bank = rowOf('Example Bank AB');
    expect(within(bank).getByText('Compliant')).toBeInTheDocument();
    expect(within(bank).getByText('Criteria adopted.')).toBeInTheDocument();
    expect(within(bank).getByText('Anna Nilsson')).toBeInTheDocument();
    expect(within(bank).getByText(/^1 Sept? 2027$/)).toBeInTheDocument();
    const finans = rowOf('Example Finans AB');
    expect(within(finans).getByText('High')).toBeInTheDocument();
    expect(within(finans).getByText('Retail compliance, a team')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(screen.getAllByText('Not mapped')).toHaveLength(3);
  });

  it('asks no status where it does not apply, and none before anyone answered', async () => {
    serve(entry({ applicability: 'not_applicable' }));
    const { unmount } = renderPanel();
    expect(
      await screen.findByText('No status is asked while it does not apply. The last one stays in the history and its gaps stay on record.'),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1);
    unmount();
    serve(entry({ applicability: 'under_assessment' }));
    renderPanel();
    expect(await screen.findByText('No status is asked until it applies.')).toBeInTheDocument();
  });

  it("reads the obligation's own standing where it is kept as a whole", async () => {
    serve(entry({ statusNote: 'Reconciliation runs daily.', firstLineOwner: ANNA, complianceContact: SARA, ownerTeam: RETAIL, process: 'Custody' }));
    renderPanel();
    const whole = (await screen.findByText('Reconciliation runs daily.')).closest('[data-status-row]') as HTMLElement;
    expect(within(whole).getByText('Anna Nilsson')).toBeInTheDocument();
    expect(within(whole).getByText('Sara Lindqvist')).toBeInTheDocument();
    expect(within(whole).getByText('Retail compliance')).toBeInTheDocument();
    expect(screen.getByText('Custody')).toBeInTheDocument();
  });

  it("saves one entity's status, basis and team owner, and only those, with its own route", async () => {
    const sent = serve(TWO);
    renderPanel();
    await screen.findByText('Example Finans AB');
    fireEvent.click(within(rowOf('Example Bank AB')).getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Where we stand at Example Bank AB' });
    await waitFor(() => expect(within(dialog).getByRole('option', { name: 'Retail compliance' })).toBeInTheDocument());
    fireEvent.change(within(dialog).getByLabelText('Compliance status'), { target: { value: 'partly_compliant' } });
    fireEvent.change(within(dialog).getByLabelText('How you assessed it'), { target: { value: 'Second-line review.' } });
    fireEvent.change(within(dialog).getByLabelText('Owner'), { target: { value: 'team:retail_compliance' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await screen.findByText('Saved.');
    expect(patches(sent)).toEqual([
      {
        path: '/api/v1/obligations/ob-1/register/entities/e-bank',
        body: { complianceStatus: 'partly_compliant', rationale: 'Second-line review.', ownerTeam: 'retail_compliance' },
      },
    ]);
  });

  it('saves how it is handled on the obligation', async () => {
    const sent = serve(TWO);
    renderPanel();
    const handle = (await screen.findByText('How we handle it')).closest('[data-handle-panel]') as HTMLElement;
    fireEvent.click(within(handle).getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'How we handle it' });
    fireEvent.change(within(dialog).getByLabelText('Process'), { target: { value: 'Research budget and yearly review' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await screen.findByText('Saved.');
    expect(patches(sent)).toEqual([{ path: '/api/v1/obligations/ob-1/register', body: { process: 'Research budget and yearly review' } }]);
  });

  it('closes without a call when nothing changed', async () => {
    const sent = serve(TWO);
    renderPanel();
    await screen.findByText('Example Finans AB');
    fireEvent.click(within(rowOf('Example Finans AB')).getByRole('button', { name: 'Edit' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(patches(sent)).toEqual([]);
  });

  it('reads a stale write from its code, merges nothing and offers a reload', async () => {
    const sent = serve(TWO, () => ({ status: 409, data: { code: 'stale_write', detail: 'Someone changed this first. Reload and try again.' } }));
    renderPanel();
    await screen.findByText('Example Finans AB');
    fireEvent.click(within(rowOf('Example Finans AB')).getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Status note'), { target: { value: 'Criteria agreed.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('Someone changed this entry while you were editing. Reload to see their version, then make your change again.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Status note')).toHaveValue('Criteria agreed.');
    const reads = sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reload' }));
    await waitFor(() => expect(sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length).toBeGreaterThan(reads));
  });

  it('says when it could not be loaded', async () => {
    serve(500);
    renderPanel();
    expect(await screen.findByText('Where we stand could not be loaded')).toBeInTheDocument();
  });
});
