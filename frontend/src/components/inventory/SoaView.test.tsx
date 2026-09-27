import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { RegisterStatementOfApplicability } from '@/features/register/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { SoaView } from './SoaView';

// The Statement of Applicability (REG-08, REG-S15): the conformance row with its own
// assessed status, then each unit with its reference, title, decision, reason, status,
// who set it and when, and its history of decisions.

const sara = { id: 'p-sara', name: 'Sara Lindqvist' };
const johan = { id: 'p-johan', name: 'Johan Berg' };
const notAssessed = { key: 'not_assessed', kind: 'not_assessed', label: 'Not assessed' };
const partly = { key: 'partly', kind: 'partially_compliant', label: 'Partly compliant' };

const statement = {
  obligationId: 'ob-std',
  conformance: {
    orgUnitId: 'e-bank',
    orgUnitName: 'Example Bank AB',
    applicability: 'applies',
    applicabilityReason: 'Certified',
    applicabilityDecidedAt: '2026-09-04T09:00:00Z',
    applicabilityDecidedBy: sara,
    complianceStatus: partly,
  },
  units: [
    {
      id: 'u-001',
      obligationId: 'ob-std',
      orgUnitId: 'e-bank',
      reference: 'SEC-001',
      title: 'Information security policy is approved by the board',
      applicability: 'applies',
      applicabilityReason: 'Board owns it',
      applicabilityDecidedAt: '2026-09-18T10:00:00Z',
      applicabilityDecidedBy: johan,
      complianceStatus: notAssessed,
      hasHistory: true,
      version: 3,
      history: [
        { applicability: 'not_applicable', reason: 'Out of scope at first', decidedAt: '2026-09-10T10:00:00Z', decidedBy: sara },
        { applicability: 'applies', reason: 'Board owns it', decidedAt: '2026-09-18T10:00:00Z', decidedBy: johan },
      ],
    },
    {
      id: 'u-044',
      obligationId: 'ob-std',
      orgUnitId: 'e-bank',
      reference: 'SEC-044',
      title: 'Backups are restored in a test once a year',
      applicability: 'under_assessment',
      applicabilityReason: null,
      applicabilityDecidedAt: null,
      applicabilityDecidedBy: null,
      complianceStatus: notAssessed,
      hasHistory: false,
      version: 1,
      history: [],
    },
  ],
  total: 2,
} as unknown as RegisterStatementOfApplicability;

function serve(answer: RegisterStatementOfApplicability | null): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'me', name: 'Me', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: ['register.read'], enrolmentPending: false } };
    if (sent.path === '/api/v1/obligations/ob-std/statement-of-applicability') {
      return answer === null ? { status: 500, data: { code: 'internal_error', detail: '' } } : { status: 200, data: answer };
    }
    return { status: 404, data: { code: 'not_found', detail: '' } };
  });
}

function renderView() {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <SoaView obligationId="ob-std" entity={{ id: 'e-bank', name: 'Example Bank AB' }} />
      </LocaleProvider>
    </Wrapper>,
  );
}

function unitRow(reference: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-soa-unit="${reference}"]`);
  if (found === null) throw new Error(`no row ${reference}`);
  return found;
}

describe('SoaView', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('asks for the statement of the one entity', async () => {
    const sent = serve(statement);
    renderView();
    await screen.findByText('2 units');
    const reads = sent.filter((call) => call.path === '/api/v1/obligations/ob-std/statement-of-applicability');
    expect(reads.map((call) => (call.params as { entity: string }).entity)).toEqual(['e-bank']);
  });

  it('shows the conformance row with its own status, and says the units do not change it', async () => {
    serve(statement);
    renderView();
    const conformance = (await screen.findByRole('heading', { name: 'Conformance for Example Bank AB' })).closest('section') as HTMLElement;
    expect(within(conformance).getByText('Applies')).toBeInTheDocument();
    expect(within(conformance).getByText('Partly compliant')).toBeInTheDocument();
    expect(within(conformance).getByText('Certified')).toBeInTheDocument();
    expect(within(conformance).getByText('Set by Sara Lindqvist')).toBeInTheDocument();
    expect(within(conformance).getByText('This is the status assessed on the obligation for the entity. The units below do not change it.')).toBeInTheDocument();
  });

  it('lists each unit with its reference, title, decision, reason, status, who and when', async () => {
    serve(statement);
    renderView();
    await screen.findByText('2 units');
    const decided = unitRow('SEC-001');
    expect(within(decided).getByText('Information security policy is approved by the board')).toBeInTheDocument();
    expect(within(decided).getAllByText('Applies')[0]?.closest('[data-pill]')).toHaveAttribute('data-pill', 'positive');
    expect(within(decided).getAllByText('Board owns it').length).toBeGreaterThan(0);
    expect(within(decided).getByText('Not assessed')).toBeInTheDocument();
    expect(within(decided).getByText('Johan Berg')).toBeInTheDocument();
    expect(within(decided).getByText(/^18 Sept? 2026$/)).toBeInTheDocument();

    const open = unitRow('SEC-044');
    // Undecided: "Not assessed" for its applicability and for its status, and nobody set it.
    expect(within(open).getAllByText('Not assessed')).toHaveLength(2);
    expect(within(open).getAllByText('None yet')).toHaveLength(4);
  });

  it('lists every decision in a unit history, oldest first, with who and when', async () => {
    serve(statement);
    renderView();
    await screen.findByText('2 units');
    const history = unitRow('SEC-001').querySelector('[data-soa-history]') as HTMLElement;
    fireEvent.click(within(history).getByText('2 decisions'));
    const entries = within(history).getAllByRole('listitem');
    expect(entries.map((entry) => entry.textContent)).toEqual([
      expect.stringContaining('Out of scope at first'),
      expect.stringContaining('Board owns it'),
    ]);
    expect(within(entries[0] as HTMLElement).getByText(/^Set by Sara Lindqvist, 10 Sept? 2026$/)).toBeInTheDocument();
    expect(within(entries[1] as HTMLElement).getByText(/^Set by Johan Berg, 18 Sept? 2026$/)).toBeInTheDocument();
  });

  it('says where units are added when the entity has none', async () => {
    serve({ ...statement, units: [], total: 0 });
    renderView();
    expect(await screen.findByText('No units for Example Bank AB')).toBeInTheDocument();
    expect(screen.getByText('Units are added and decided on the Units tab.')).toBeInTheDocument();
  });

  it('offers a retry when the statement cannot be read', async () => {
    serve(null);
    renderView();
    expect(await screen.findByText('The Statement of Applicability could not be loaded')).toBeInTheDocument();
  });
});
