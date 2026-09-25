import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { RegisterEntityStatus, RegisterEntry } from '@/features/register/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { answersOf, ObligationApplicabilityPanel } from './ObligationApplicabilityPanel';

// "Does it apply to us?" (design/screens/tenant-obligation.html; REG-01, D-75):
// one row per legal entity where the obligation spans several, the answer set
// after a confirmation step, nothing sent on cancel, no step-up, and the stale
// write read from its code. Every instant is fixed.

const ME = { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false };
const SARA = { id: 'u1', name: 'Sara Lindqvist' };
const NOT_ASSESSED = { key: 'not_assessed', kind: 'not_assessed', label: 'Not assessed' };

function entity(id: string, name: string, patch: Partial<RegisterEntityStatus> = {}): RegisterEntityStatus {
  return {
    orgUnitId: id,
    orgUnitName: name,
    applicability: 'applies',
    applicabilityReason: 'We give advice and manage portfolios.',
    applicabilityDecidedAt: '2026-09-18T08:30:00Z',
    applicabilityDecidedBy: SARA,
    complianceStatus: NOT_ASSESSED,
    statusNote: null,
    riskRating: null,
    owner: null,
    ownerTeam: null,
    process: null,
    system: null,
    evidenceLocation: null,
    nextReviewDate: null,
    version: 2,
    ...patch,
  };
}

function entry(patch: Partial<RegisterEntry> = {}): RegisterEntry {
  return {
    obligationId: 'ob-1',
    applicability: 'under_assessment',
    applicabilityReason: null,
    applicabilityDecidedAt: null,
    applicabilityDecidedBy: null,
    complianceStatus: NOT_ASSESSED,
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
    version: 0,
    updatedAt: null,
    ...patch,
  };
}

const SPAN = [
  { orgUnitId: 'e-bank', orgUnitName: 'Example Bank AB' },
  { orgUnitId: 'e-liv', orgUnitName: 'Example Liv AB' },
];

function serve(read: RegisterEntry | number, span = SPAN, write: (sent: Sent) => { status: number; data?: unknown } = () => ({ status: 200, data: {} })): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: ME };
    if (sent.path === '/api/v1/obligations/ob-1/register/entities') return { status: 200, data: span };
    if (sent.method === 'put') return write(sent);
    if (typeof read === 'number') return { status: read, data: { detail: 'no', code: 'server_error' } };
    return { status: 200, data: read };
  });
}

function renderPanel(permissions: string[] = ['register.read', 'applicability.approve']) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <ObligationApplicabilityPanel obligationId="ob-1" />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

const puts = (sent: Sent[]) => sent.filter((call) => call.method === 'put');

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('session-token');
});

describe('answersOf', () => {
  it('answers for the obligation as a whole where it spans one entity or none', () => {
    expect(answersOf(entry(), [SPAN[0]!]).map((answer) => answer.orgUnitId)).toEqual([null]);
    expect(answersOf(entry(), []).map((answer) => answer.orgUnitId)).toEqual([null]);
  });

  it('answers per entity where it spans several, an unanswered one at version 0, and keeps a whole answer someone gave', () => {
    const bank = entity('e-bank', 'Example Bank AB', { version: 3 });
    expect(answersOf(entry({ entities: [bank] }), SPAN).map((answer) => [answer.orgUnitId, answer.applicability, answer.version])).toEqual([
      ['e-bank', 'applies', 3],
      ['e-liv', 'under_assessment', 0],
    ]);
    const decided = entry({ applicability: 'applies', applicabilityReason: 'Both entities advise.', version: 4 });
    expect(answersOf(decided, SPAN).map((answer) => answer.orgUnitId)).toEqual([null, 'e-bank', 'e-liv']);
  });

  it('keeps an answered entity the obligation no longer spans, after the spanned ones', () => {
    const fonder = entity('e-fonder', 'Example Fonder AB');
    expect(answersOf(entry({ entities: [fonder] }), SPAN).map((answer) => answer.name)).toEqual(['Example Bank AB', 'Example Liv AB', 'Example Fonder AB']);
  });
});

describe('ObligationApplicabilityPanel', () => {
  it('reads one row per entity with its pill, reason, who and when, and offers nothing without applicability.approve', async () => {
    serve(entry({ entities: [entity('e-bank', 'Example Bank AB')] }));
    renderPanel(['register.read']);
    const bank = await screen.findByText('Example Bank AB');
    const row = bank.closest('[data-applicability-row]') as HTMLElement;
    expect(within(row).getByText('Applies')).toBeInTheDocument();
    expect(within(row).getByText(/^Set by Sara Lindqvist, 18 Sept? 2026$/)).toBeInTheDocument();
    expect(within(row).getByText('We give advice and manage portfolios.')).toBeInTheDocument();
    const liv = screen.getByText('Example Liv AB').closest('[data-applicability-row]') as HTMLElement;
    expect(within(liv).getByText('Not assessed')).toBeInTheDocument();
    expect(within(liv).getByText('Nobody has decided yet.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('Whether a rule applies and whether we comply are two separate facts, recorded separately.')).toBeInTheDocument();
  });

  it('answers for the whole obligation where it spans one entity, with no entity heading', async () => {
    serve(entry(), [SPAN[0]!]);
    renderPanel();
    expect(await screen.findByText('Nobody has decided yet.')).toBeInTheDocument();
    expect(screen.queryByText('Example Bank AB')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Decide' }));
    expect(screen.getByRole('dialog', { name: 'Does it apply to us?' })).toBeInTheDocument();
  });

  it('asks to confirm before anything is stored, and a cancel stores nothing', async () => {
    const sent = serve(entry({ entities: [entity('e-bank', 'Example Bank AB')] }));
    renderPanel();
    await screen.findByText('Example Liv AB');
    const liv = screen.getByText('Example Liv AB').closest('[data-applicability-row]') as HTMLElement;
    fireEvent.click(within(liv).getByRole('button', { name: 'Decide' }));
    const form = screen.getByRole('dialog', { name: 'Does it apply to Example Liv AB?' });
    expect(within(form).getByRole('button', { name: 'Continue' })).toBeDisabled();
    fireEvent.change(within(form).getByLabelText('Decision'), { target: { value: 'not_applicable' } });
    fireEvent.change(within(form).getByLabelText('Reason'), { target: { value: 'No insurance advice from Liv.' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Continue' }));

    const confirm = screen.getByRole('dialog', { name: 'Set "Does not apply" for Example Liv AB?' });
    expect(confirm).toHaveAccessibleDescription(
      'It is stored at once in your name, with your reason, and kept in the audit log. It was "Not assessed". The compliance status and gaps stay as they are and return if it applies again.',
    );
    fireEvent.click(within(confirm).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(puts(sent)).toEqual([]);
  });

  it('stores the confirmed answer for the entity at once and says so', async () => {
    const sent = serve(entry({ entities: [entity('e-bank', 'Example Bank AB')] }));
    renderPanel();
    const bank = (await screen.findByText('Example Bank AB')).closest('[data-applicability-row]') as HTMLElement;
    fireEvent.click(within(bank).getByRole('button', { name: 'Change' }));
    const form = screen.getByRole('dialog', { name: 'Does it apply to Example Bank AB?' });
    expect(within(form).getByLabelText('Reason')).toHaveValue('We give advice and manage portfolios.');
    fireEvent.change(within(form).getByLabelText('Decision'), { target: { value: 'not_applicable' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Continue' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Set applicability' }));

    await screen.findByText('Saved: Does not apply.');
    expect(puts(sent)).toEqual([
      expect.objectContaining({
        path: '/api/v1/obligations/ob-1/applicability',
        body: { applicability: 'not_applicable', reason: 'We give advice and manage portfolios.', orgUnitId: 'e-bank' },
      }),
    ]);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('reads a stale write from its code and offers a reload that refetches', async () => {
    const sent = serve(entry({ entities: [entity('e-bank', 'Example Bank AB')] }), SPAN, () => ({
      status: 409,
      data: { code: 'stale_write', detail: 'Someone changed this first. Reload and try again.' },
    }));
    renderPanel();
    const bank = (await screen.findByText('Example Bank AB')).closest('[data-applicability-row]') as HTMLElement;
    fireEvent.click(within(bank).getByRole('button', { name: 'Change' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Continue' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Set applicability' }));
    expect(await screen.findByText('Someone changed this answer while you were deciding. Reload to see theirs, then decide again.')).toBeInTheDocument();
    const reads = sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length;
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    await waitFor(() => expect(sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length).toBeGreaterThan(reads));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders any other refusal in place', async () => {
    serve(entry({ entities: [entity('e-bank', 'Example Bank AB')] }), SPAN, () => ({
      status: 404,
      data: { code: 'not_found', detail: 'That legal entity is not one this obligation spans.' },
    }));
    renderPanel();
    const bank = (await screen.findByText('Example Bank AB')).closest('[data-applicability-row]') as HTMLElement;
    fireEvent.click(within(bank).getByRole('button', { name: 'Change' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Continue' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Set applicability' }));
    expect(await screen.findByText('That legal entity is not one this obligation spans.')).toBeInTheDocument();
  });

  it('says when the answers could not be loaded', async () => {
    serve(500);
    renderPanel();
    expect(await screen.findByText('Does it apply to us could not be loaded')).toBeInTheDocument();
  });
});
