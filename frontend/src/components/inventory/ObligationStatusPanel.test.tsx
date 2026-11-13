import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { RegisterEntityStatus, RegisterEntry, RegisterPanels } from '@/features/register/types';
import { withPanels } from '@/features/register/testing';
import { installAdapter, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';
import { renderWith } from '@/shared/testing/render';

import { changesOf, ObligationHandlePanel } from './ObligationStatusPanel';

// "How we handle it" (design/screens/tenant-obligation.html; REG-02): the
// process, system and evidence for the whole obligation, one line with "Map it"
// while nothing is mapped, edits behind register.edit sending only what moved.
// Where each company stands is drawn and tested in ObligationPositionPanel.

const ME = { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false };
const COMPLIANT = { key: 'compliant', kind: 'compliant', label: 'Compliant' };
const SARA = { id: 'p-sara', name: 'Sara Lindqvist' };

function entity(id: string, name: string): RegisterEntityStatus {
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
  };
}

function entry(patch: Partial<RegisterEntry> = {}): RegisterEntry {
  return {
    obligationId: 'ob-1',
    interpretation: { obligationId: 'ob-1', current: null, earlier: [] },
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

const POLICY = {
  id: 'l-1',
  kind: { key: 'policy', kind: null, label: 'Policy' },
  label: 'Research and inducements policy',
  url: null,
  externalRef: 'POL-014',
  externalSystem: null,
  internalItemId: 'i-1',
  createdBy: SARA,
  createdAt: '2026-09-18T09:00:00Z',
};

function serve(read: RegisterEntry | number, links: unknown[] = []): Sent[] {
  const page = { items: links, total: links.length };
  return installAdapter((sent) => {
    if (sent.method === 'patch') return { status: 200, data: {} };
    if (typeof read === 'number') return { status: read, data: { detail: 'no', code: 'server_error' } };
    if (sent.path.endsWith('/internal-links')) return { status: 200, data: page };
    return { status: 200, data: withPanels(read, { internalLinks: page as RegisterPanels['internalLinks'] }) };
  }, { me: ME });
}

const patches = (sent: Sent[]) => sent.filter((call) => call.method === 'patch').map((call) => ({ path: call.path, body: call.body }));

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

describe('ObligationHandlePanel', () => {
  it('is one line with "Map it" and "Link an item" while nothing is mapped or linked, and maps it', async () => {
    const sent = serve(entry());
    renderWith(<ObligationHandlePanel obligationId="ob-1" />, { permissions: ['register.read', 'register.edit'] });
    const line = (await screen.findByText('Not mapped to a process, system or evidence yet.')).closest('[data-handle-empty]') as HTMLElement;
    expect(screen.queryByRole('heading', { name: 'How we handle it' })).toBeNull();
    // The linked items share the line: no second "nothing yet" for them.
    expect(await within(line).findByRole('button', { name: 'Link an item' })).toBeInTheDocument();
    expect(screen.getAllByText(/yet\.$/)).toHaveLength(1);
    fireEvent.click(within(line).getByRole('button', { name: 'Map it' }));
    const dialog = screen.getByRole('dialog', { name: 'How we handle it' });
    fireEvent.change(within(dialog).getByLabelText('Process'), { target: { value: 'Research budget and yearly review' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await screen.findByText('Saved.');
    expect(patches(sent)).toEqual([{ path: '/api/v1/obligations/ob-1/register', body: { process: 'Research budget and yearly review' } }]);
  });

  it('reads what is mapped under its heading, "Not mapped" where a field is empty, and offers Edit only with register.edit', async () => {
    serve(entry({ process: 'Custody reconciliation', evidenceLocation: 'Compliance share' }));
    const { unmount } = renderWith(<ObligationHandlePanel obligationId="ob-1" />, { permissions: ['register.read'] });
    const part = (await screen.findByRole('heading', { name: 'How we handle it' })).closest('[data-handle-panel]') as HTMLElement;
    expect(within(part).getByText('Custody reconciliation')).toBeInTheDocument();
    expect(within(part).getByText('Not mapped')).toBeInTheDocument();
    expect(within(part).queryByRole('button')).toBeNull();
    unmount();
    serve(entry({ process: 'Custody reconciliation' }));
    renderWith(<ObligationHandlePanel obligationId="ob-1" />, { permissions: ['register.read', 'register.edit'] });
    expect(await screen.findByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('holds the linked internal items under its heading, with "Link an item" beneath them', async () => {
    serve(entry({ process: 'Custody reconciliation' }), [POLICY]);
    renderWith(<ObligationHandlePanel obligationId="ob-1" />, { permissions: ['register.read', 'register.edit'] });
    const link = await screen.findByText('Research and inducements policy');
    const part = screen.getByRole('heading', { name: 'How we handle it' }).closest('[data-handle-panel]') as HTMLElement;
    expect(part.contains(link)).toBe(true);
    expect(within(part).getByText('Custody reconciliation')).toBeInTheDocument();
    expect(within(part).getByRole('button', { name: 'Link an item' })).toBeInTheDocument();
    expect(within(part).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('keeps "Map it" on its own line, under the heading, when items are linked but nothing is mapped', async () => {
    serve(entry(), [POLICY]);
    renderWith(<ObligationHandlePanel obligationId="ob-1" />, { permissions: ['register.read', 'register.edit'] });
    await screen.findByText('Research and inducements policy');
    const part = screen.getByRole('heading', { name: 'How we handle it' }).closest('[data-handle-panel]') as HTMLElement;
    const line = within(part).getByText('Not mapped to a process, system or evidence yet.').closest('[data-handle-empty]') as HTMLElement;
    expect(within(line).getByRole('button', { name: 'Map it' })).toBeInTheDocument();
    // Map it is the one way in while nothing is mapped: no Edit beside the heading too.
    expect(within(part).queryByRole('button', { name: 'Edit' })).toBeNull();
  });

  it('draws nothing to press while nothing is mapped for someone who may not edit', async () => {
    serve(entry());
    renderWith(<ObligationHandlePanel obligationId="ob-1" />, { permissions: ['register.read'] });
    await screen.findByText('Not mapped to a process, system or evidence yet.');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('says when it could not be loaded', async () => {
    serve(500);
    renderWith(<ObligationHandlePanel obligationId="ob-1" />, { permissions: ['register.read'] });
    expect(await screen.findByText('Where we stand could not be loaded')).toBeInTheDocument();
  });
});
