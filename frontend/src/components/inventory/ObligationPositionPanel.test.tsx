import type { QueryClient } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { RegisterEntityStatus, RegisterEntry, RegisterGap } from '@/features/register/types';
import { withPanels } from '@/features/register/testing';
import { installAdapter, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';
import { renderWith } from '@/shared/testing/render';

import { ObligationPositionPanel, positionBlocks } from './ObligationPositionPanel';

// "Our position" (design/screens/tenant-obligation.html; REG-01, REG-02, D-42,
// D-75, D-141): one block per company with "Does it apply" and, where it applies,
// "Where we stand"; the answer set in one step through the dialog "What applies"
// uses, its reason suggested for a company nobody answered, nothing sent on
// cancel, no step-up; the standing edited behind register.edit, sending only
// what changed; each stale write read from its code. Every instant is fixed.

const ME = { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false };
const SARA = { id: 'p-sara', name: 'Sara Lindqvist' };
const ANNA = { id: 'p-anna', name: 'Anna Nilsson' };
const COMPLIANT = { key: 'compliant', kind: 'compliant', label: 'Compliant' };
const PARTLY = { key: 'partly_compliant', kind: 'partly', label: 'Partly compliant' };
const NOT_ASSESSED = { key: 'not_assessed', kind: 'not_assessed', label: 'Not assessed' };
const HIGH = { key: 'high', kind: null, label: 'High' };
const RETAIL = { key: 'retail_compliance', kind: null, label: 'Retail compliance' };

function entity(id: string, name: string, patch: Partial<RegisterEntityStatus> = {}): RegisterEntityStatus {
  return {
    orgUnitId: id,
    orgUnitName: name,
    applicability: 'applies',
    applicabilityReason: 'We give advice and manage portfolios.',
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
    version: 2,
    ...patch,
  };
}

function entry(patch: Partial<RegisterEntry> = {}): RegisterEntry {
  return {
    obligationId: 'ob-1',
    interpretation: { obligationId: 'ob-1', current: null, earlier: [] },
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

function gap(id: string, orgUnitId: string | null, kind: string): RegisterGap {
  return {
    id,
    obligationId: 'ob-1',
    orgUnitId,
    unitId: null,
    title: `Gap ${id}`,
    description: null,
    severity: { key: 'high', kind: 'high', label: 'High' },
    source: { key: 'assessment', kind: null, label: 'Self-assessment' },
    status: { key: kind, kind, label: kind },
    owner: SARA,
    ownerTeam: null,
    targetDate: '2026-11-30',
    remediation: null,
    identifiedAt: '2026-09-12T08:00:00Z',
    identifiedBy: SARA,
    riskAcceptance: null,
    version: 1,
  };
}

const SPAN = [
  { orgUnitId: 'e-bank', orgUnitName: 'Example Bank AB' },
  { orgUnitId: 'e-liv', orgUnitName: 'Example Liv AB' },
];

// The bank applies and stands partly compliant with a note, an owner, a review date, a risk
// and two open gaps; the insurer nobody has answered for.
const WORKED = entry({
  applicability: 'applies',
  complianceStatus: PARTLY,
  entities: [
    entity('e-bank', 'Example Bank AB', {
      complianceStatus: PARTLY,
      statusNote: 'Criteria agreed; the first yearly assessment is not done yet.',
      owner: ANNA,
      nextReviewDate: '2026-11-30',
      riskRating: HIGH,
      process: 'Research budget',
    }),
  ],
});
const GAPS = { items: [gap('g-1', 'e-bank', 'open'), gap('g-2', 'e-bank', 'remediating'), gap('g-3', 'e-bank', 'closed'), gap('g-4', 'e-liv', 'open')], total: 4 };

// The obligation's regulation, and what the insurer's regulations say brings it into scope.
const REGULATIONS = '/api/v1/applicability/regulations';
const ORG_UNITS = '/api/v1/tenant/org-units';
const INSTRUMENT = { id: 'i-fffs', key: 'fffs-2017-2', shortName: 'FFFS 2017:2' };
const regulation = (key: string, shortName: string) => ({
  instrument: { id: `id-${key}`, key, shortName, jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' } },
  offered: 3,
  applies: 0,
  notApplicable: 0,
  underAssessment: 3,
  toDecide: 3,
  through: { term: { key: 'insurance', label: 'Insurance', kind: null, dimension: 'regime' }, lines: ['Tillstånd att driva försäkringsrörelse'] },
});
// A neighbour the search also finds comes first, so the entry is taken by its key.
const LIV_REGULATIONS = [regulation('fffs-2017-20', 'FFFS 2017:20'), regulation(INSTRUMENT.key, INSTRUMENT.shortName)];
const LIV_UNIT = { id: 'e-liv', kind: 'legal_entity', name: 'Example Liv AB', registerEntry: { authority: { key: 'fi', name: 'Finansinspektionen' }, readAt: '2026-11-11T03:17:00Z' } };
const SUGGESTED = "Within the scope of its licence Tillstånd att driva försäkringsrörelse, which brings Insurance into scope. Read from Finansinspektionen's register on 11 Nov 2026.";

type Write = (sent: Sent) => { status: number; data?: unknown };
const ok: Write = () => ({ status: 200, data: {} });

function serve(read: RegisterEntry | number, span = SPAN, write: Write = ok, regulations: unknown[] = LIV_REGULATIONS): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/obligations/ob-1') return { status: 200, data: { id: 'ob-1', instrument: INSTRUMENT } };
    if (sent.path === REGULATIONS) return { status: 200, data: { items: regulations, total: regulations.length } };
    if (sent.path === ORG_UNITS) return { status: 200, data: { items: [LIV_UNIT], total: 1 } };
    if (sent.path === '/api/v1/obligations/ob-1/register/entities') return { status: 200, data: span };
    if (sent.path === '/api/v1/obligations/ob-1/gaps') return { status: 200, data: GAPS };
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: [ANNA, SARA] };
    if (sent.path === '/api/v1/vocab/compliance_status') return { status: 200, data: { items: [COMPLIANT, PARTLY, NOT_ASSESSED], total: 3 } };
    if (sent.path === '/api/v1/vocab/risk_rating') return { status: 200, data: { items: [HIGH], total: 1 } };
    if (sent.path === '/api/v1/vocab/team') return { status: 200, data: { items: [RETAIL], total: 1 } };
    if (sent.method === 'put' || sent.method === 'patch') return write(sent);
    if (typeof read === 'number') return { status: read, data: { detail: 'no', code: 'server_error' } };
    return { status: 200, data: withPanels(read, { spannedEntities: span, gaps: GAPS }) };
  }, { me: ME });
}

const ALL = ['register.read', 'register.edit', 'applicability.approve'];

let client: QueryClient;

function renderPanel(permissions: string[] = ALL) {
  const view = renderWith(<ObligationPositionPanel obligationId="ob-1" />, { permissions });
  client = view.queryClient;
  return view;
}

/** Where the first read under a key stands: settled reads prove a late answer had its chance. */
const queryState = (prefix: readonly unknown[]) => client.getQueryCache().findAll({ queryKey: prefix })[0]?.state.status;

/** One company's block, by the heading that names it. */
function block(name: string): HTMLElement {
  return screen.getByRole('heading', { level: 3, name }).closest('[data-position-entity]') as HTMLElement;
}
const answerOf = (name: string) => block(name).querySelector('[data-applicability-row]') as HTMLElement;
const standingOf = (name: string) => block(name).querySelector('[data-status-row]') as HTMLElement;
const writes = (sent: Sent[]) => sent.filter((call) => call.method === 'put' || call.method === 'patch');

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('session-token');
});

describe('positionBlocks', () => {
  it('gives each company its answer and, where it applies, its standing', () => {
    expect(positionBlocks(WORKED, SPAN).map((row) => [row.key, row.answer?.applicability, row.standing === null ? null : 'stands'])).toEqual([
      ['whole', 'applies', null],
      ['e-bank', 'applies', 'stands'],
      ['e-liv', 'under_assessment', null],
    ]);
  });

  it('keeps the obligation\'s own standing where it is kept as a whole and applies, and none before', () => {
    const whole = entry({ applicability: 'applies' });
    expect(positionBlocks(whole, [SPAN[0]!])).toEqual([expect.objectContaining({ key: 'whole', name: null, standing: whole })]);
    expect(positionBlocks(entry(), [SPAN[0]!])).toEqual([expect.objectContaining({ key: 'whole', standing: null })]);
  });

  it('gives a company that applies a block of its own where only the whole obligation is answered', () => {
    const bank = entity('e-bank', 'Example Bank AB');
    expect(positionBlocks(entry({ entities: [bank] }), [SPAN[0]!]).map((row) => [row.key, row.answer === null, row.standing])).toEqual([
      ['whole', false, null],
      ['e-bank', true, bank],
    ]);
  });
});

describe('ObligationPositionPanel', () => {
  it('draws one block per company: its answer with who set it and why, and where it applies, where it stands', async () => {
    serve(WORKED);
    renderPanel(['register.read']);
    expect(screen.getByRole('heading', { level: 2, name: 'Our position' })).toBeInTheDocument();
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    expect([...document.querySelectorAll('[data-position-entity] > h3')].map((heading) => heading.textContent)).toEqual([
      'The obligation as a whole',
      'Example Bank AB',
      'Example Liv AB',
    ]);

    const bank = answerOf('Example Bank AB');
    expect(within(bank).getByText('Does it apply')).toBeInTheDocument();
    expect(within(bank).getByText('Applies')).toHaveAttribute('data-pill');
    expect(within(bank).getByText(/^Set by Sara Lindqvist, 18 Sept? 2026$/)).toBeInTheDocument();
    expect(within(bank).getByText('We give advice and manage portfolios.')).toBeInTheDocument();

    // One pill in the standing: the status. Owner, review and the open gaps (not the closed
    // one, not the insurer's) ride on its line; the note under it; the rest in "More".
    const stands = standingOf('Example Bank AB');
    expect([...stands.querySelectorAll('[data-pill]')].map((pill) => pill.textContent)).toEqual(['Partly compliant']);
    expect(within(stands).getByText('Owner Anna Nilsson')).toBeInTheDocument();
    expect(within(stands).getByText(/^Next review 30 Nov 2026$/)).toBeInTheDocument();
    expect(await within(stands).findByText('2 open gaps')).toBeInTheDocument();
    expect(within(stands).getByText('Criteria agreed; the first yearly assessment is not done yet.')).toBeInTheDocument();
    expect(within(stands).queryByText('High')).toBeNull();
    fireEvent.click(within(stands).getByRole('button', { name: 'More' }));
    expect(within(stands).getByText('High')).toBeInTheDocument();
    expect(within(stands).getByText('Research budget')).toBeInTheDocument();

    const liv = answerOf('Example Liv AB');
    expect(within(liv).getByText('Not assessed')).toBeInTheDocument();
    expect(within(liv).getByText('Nobody has decided yet.')).toBeInTheDocument();
    expect(standingOf('Example Liv AB')).toBeNull();
    // Without applicability.approve or register.edit there is nothing to press but "More".
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual(['More']);
  });

  it('counts no gaps for someone who may not read the register', async () => {
    const sent = serve(WORKED);
    renderPanel(['applicability.approve']);
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    expect(within(standingOf('Example Bank AB')).queryByText(/open gaps?/)).toBeNull();
    expect(sent.some((call) => call.path.endsWith('/gaps'))).toBe(false);
  });

  it('answers for the whole obligation where it spans one company, with no heading, and keeps its standing there', async () => {
    serve(entry({ applicability: 'applies', applicabilityReason: 'We advise.', complianceStatus: COMPLIANT, statusNote: 'Reconciliation runs daily.', firstLineOwner: ANNA, complianceContact: SARA, ownerTeam: RETAIL }), [SPAN[0]!]);
    renderPanel();
    const whole = (await screen.findByText('Reconciliation runs daily.')).closest('[data-status-row]') as HTMLElement;
    expect(whole).toHaveAttribute('data-status-row', 'whole');
    expect(screen.queryByRole('heading', { level: 3 })).toBeNull();
    expect(within(whole).getByText('Owner Anna Nilsson')).toBeInTheDocument();
    fireEvent.click(within(whole).getByRole('button', { name: 'More' }));
    expect(within(whole).getByText('Sara Lindqvist')).toBeInTheDocument();
    expect(within(whole).getByText('Retail compliance')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Change' }));
    expect(screen.getByRole('dialog', { name: 'Does it apply to us?' })).toBeInTheDocument();
  });

  it('decides in one step: nothing is sent before its button, and a cancel stores nothing', async () => {
    const sent = serve(WORKED);
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Liv AB' });
    fireEvent.click(within(answerOf('Example Liv AB')).getByRole('button', { name: 'Decide' }));
    const form = screen.getByRole('dialog', { name: 'Does it apply to Example Liv AB?' });
    fireEvent.click(within(form).getByRole('button', { name: 'Does not apply' }));
    expect(within(form).getByRole('button', { name: 'Set to Does not apply' })).toBeDisabled();
    fireEvent.change(within(form).getByLabelText('Reason'), { target: { value: 'No insurance advice from Liv.' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(writes(sent)).toEqual([]);
  });

  it("suggests the reason for a company nobody answered from that company's regulations, read when the dialog opens, and stores it at once", async () => {
    const sent = serve(WORKED);
    const { queryClient } = renderPanel();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    await screen.findByRole('heading', { level: 3, name: 'Example Liv AB' });
    expect(sent.some((call) => call.path === REGULATIONS)).toBe(false);
    fireEvent.click(within(answerOf('Example Liv AB')).getByRole('button', { name: 'Decide' }));
    const form = screen.getByRole('dialog', { name: 'Does it apply to Example Liv AB?' });
    expect(within(form).getByText('Now: to decide')).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Applies' })).toHaveAttribute('aria-pressed', 'true');
    // Empty and usable while the read is out, then the suggestion.
    expect(within(form).getByLabelText('Reason')).toHaveValue('');
    await within(form).findByText('Suggested from the licence facts');
    expect(within(form).getByLabelText('Reason')).toHaveValue(SUGGESTED);
    expect(sent.filter((call) => call.path === REGULATIONS).map((call) => call.params)).toEqual([{ orgUnitId: 'e-liv', q: 'FFFS 2017:2' }]);

    fireEvent.click(within(form).getByRole('button', { name: 'Set to Applies' }));
    await screen.findByText('Saved: Applies.');
    expect(writes(sent)).toEqual([expect.objectContaining({ path: '/api/v1/obligations/ob-1/applicability', body: { applicability: 'applies', reason: SUGGESTED, orgUnitId: 'e-liv' } })]);
    expect(screen.queryByRole('dialog')).toBeNull();
    // The page's own reads, What applies, the obligation lists and the regulation roll-up (under the register's) are read again.
    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toEqual(expect.arrayContaining([['register'], ['applies'], ['library', 'obligations']]));
  });

  it('suggests nothing where the company has no entry for this regulation', async () => {
    serve(WORKED, SPAN, ok, [regulation('fffs-2017-20', 'FFFS 2017:20')]);
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Liv AB' });
    fireEvent.click(within(answerOf('Example Liv AB')).getByRole('button', { name: 'Decide' }));
    const form = screen.getByRole('dialog');
    await waitFor(() => expect(queryState(['applies', 'regulations'])).toBe('success'));
    expect(within(form).getByLabelText('Reason')).toHaveValue('');
    expect(within(form).queryByText('Suggested from the licence facts')).toBeNull();
  });

  it('never puts a late suggestion over what the person started typing', async () => {
    serve(WORKED);
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Liv AB' });
    fireEvent.click(within(answerOf('Example Liv AB')).getByRole('button', { name: 'Decide' }));
    const form = screen.getByRole('dialog');
    fireEvent.change(within(form).getByLabelText('Reason'), { target: { value: 'Liv sells no investment products.' } });
    await waitFor(() => expect([queryState(['applies', 'regulations']), queryState(['tenant', 'org-units'])]).toEqual(['success', 'success']));
    expect(within(form).getByLabelText('Reason')).toHaveValue('Liv sells no investment products.');
    expect(within(form).queryByText('Suggested from the licence facts')).toBeNull();
  });

  it('reads no suggestion without register.read', async () => {
    const sent = serve(WORKED);
    renderPanel(['applicability.approve']);
    await screen.findByRole('heading', { level: 3, name: 'Example Liv AB' });
    fireEvent.click(within(answerOf('Example Liv AB')).getByRole('button', { name: 'Decide' }));
    await waitFor(() => expect(queryState(['library', 'obligation'])).toBe('success'));
    expect(within(screen.getByRole('dialog')).getByLabelText('Reason')).toHaveValue('');
    expect(sent.some((call) => call.path === REGULATIONS || call.path === ORG_UNITS)).toBe(false);
  });

  it("changes a company's answer from its stored answer and reason, with no suggestion read", async () => {
    const sent = serve(WORKED);
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    fireEvent.click(within(answerOf('Example Bank AB')).getByRole('button', { name: 'Change' }));
    const form = screen.getByRole('dialog', { name: 'Does it apply to Example Bank AB?' });
    expect(within(form).getByText('Now: Applies')).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Applies' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(form).getByLabelText('Reason')).toHaveValue('We give advice and manage portfolios.');
    expect(within(form).queryByText('Suggested from the licence facts')).toBeNull();
    // The Applies reason never goes with Does not apply: the field empties until the person gives one.
    fireEvent.click(within(form).getByRole('button', { name: 'Does not apply' }));
    expect(within(form).getByLabelText('Reason')).toHaveValue('');
    expect(within(form).getByRole('button', { name: 'Set to Does not apply' })).toBeDisabled();
    fireEvent.change(within(form).getByLabelText('Reason'), { target: { value: 'The bank gives no advice under this rule.' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Set to Does not apply' }));

    await screen.findByText('Saved: Does not apply.');
    expect(writes(sent)).toEqual([
      expect.objectContaining({
        path: '/api/v1/obligations/ob-1/applicability',
        body: { applicability: 'not_applicable', reason: 'The bank gives no advice under this rule.', orgUnitId: 'e-bank' },
      }),
    ]);
    expect(sent.some((call) => call.path === REGULATIONS)).toBe(false);
  });

  it('opens a row a colleague set to Not assessed on Applies with the suggestion, saying what it is now', async () => {
    const waiting = entity('e-liv', 'Example Liv AB', { applicability: 'under_assessment', applicabilityReason: 'Waiting for the legal opinion.' });
    serve({ ...WORKED, entities: [...WORKED.entities, waiting] });
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Liv AB' });
    fireEvent.click(within(answerOf('Example Liv AB')).getByRole('button', { name: 'Decide' }));
    const form = screen.getByRole('dialog', { name: 'Does it apply to Example Liv AB?' });
    expect(within(form).getByText('Now: Not assessed')).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Applies' })).toHaveAttribute('aria-pressed', 'true');
    await within(form).findByText('Suggested from the licence facts');
    expect(within(form).getByLabelText('Reason')).toHaveValue(SUGGESTED);
    // Back on its stored answer, the stored reason.
    fireEvent.click(within(form).getByRole('button', { name: 'Not assessed' }));
    expect(within(form).getByLabelText('Reason')).toHaveValue('Waiting for the legal opinion.');
  });

  it('answers for the obligation as a whole with no company and no suggestion, "Not assessed" included', async () => {
    const sent = serve(entry({ version: 3 }), [SPAN[0]!]);
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Decide' }));
    const form = screen.getByRole('dialog', { name: 'Does it apply to us?' });
    expect(within(form).getByText('Now: to decide')).toBeInTheDocument();
    expect(within(form).getByLabelText('Reason')).toHaveValue('');
    fireEvent.click(within(form).getByRole('button', { name: 'Not assessed' }));
    fireEvent.change(within(form).getByLabelText('Reason'), { target: { value: 'Waiting for the legal opinion.' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Set to Not assessed' }));
    await screen.findByText('Saved: Not assessed.');
    expect(writes(sent)).toEqual([expect.objectContaining({ path: '/api/v1/obligations/ob-1/applicability', body: { applicability: 'under_assessment', reason: 'Waiting for the legal opinion.' } })]);
    expect(sent.some((call) => call.path === REGULATIONS)).toBe(false);
  });

  it('reads a stale answer from its code, re-reads the register and keeps what the person typed', async () => {
    const sent = serve(WORKED, SPAN, () => ({ status: 409, data: { code: 'stale_write', detail: 'Someone changed this first. Reload and try again.' } }));
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    const reads = () => sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length;
    const before = reads();
    fireEvent.click(within(answerOf('Example Bank AB')).getByRole('button', { name: 'Change' }));
    const form = screen.getByRole('dialog');
    fireEvent.change(within(form).getByLabelText('Reason'), { target: { value: 'We advise.' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Set to Applies' }));
    expect(await within(form).findByText('Someone changed this answer while you were deciding. Check what it is now, then set yours again.')).toBeInTheDocument();
    await waitFor(() => expect(reads()).toBeGreaterThan(before));
    expect(within(form).getByLabelText('Reason')).toHaveValue('We advise.');
  });

  it('renders any other refusal of an answer in place', async () => {
    serve(WORKED, SPAN, () => ({ status: 404, data: { code: 'not_found', detail: 'That legal entity is not one this obligation spans.' } }));
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    fireEvent.click(within(answerOf('Example Bank AB')).getByRole('button', { name: 'Change' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Set to Applies' }));
    expect(await screen.findByText('That legal entity is not one this obligation spans.')).toBeInTheDocument();
  });

  it("saves one company's status, basis and team owner, and only those, with its own route", async () => {
    const sent = serve(WORKED);
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    fireEvent.click(within(standingOf('Example Bank AB')).getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Where we stand at Example Bank AB' });
    await waitFor(() => expect(within(dialog).getByRole('option', { name: 'Retail compliance' })).toBeInTheDocument());
    fireEvent.change(within(dialog).getByLabelText('Compliance status'), { target: { value: 'compliant' } });
    fireEvent.change(within(dialog).getByLabelText('How you assessed it'), { target: { value: 'Second-line review.' } });
    fireEvent.change(within(dialog).getByLabelText('Owner'), { target: { value: 'team:retail_compliance' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await screen.findByText('Saved.');
    expect(writes(sent).map((call) => ({ path: call.path, body: call.body }))).toEqual([
      { path: '/api/v1/obligations/ob-1/register/entities/e-bank', body: { complianceStatus: 'compliant', rationale: 'Second-line review.', ownerTeam: 'retail_compliance' } },
    ]);
  });

  it("saves the obligation's own standing where it is kept as a whole, and closes without a call when nothing changed", async () => {
    const sent = serve(entry({ applicability: 'applies', complianceStatus: COMPLIANT, version: 5 }), [SPAN[0]!]);
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Where we stand' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(within(screen.getByRole('dialog')).getByLabelText('Status note'), { target: { value: 'Checked.' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save' }));
    await screen.findByText('Saved.');
    expect(writes(sent).map((call) => ({ path: call.path, body: call.body }))).toEqual([{ path: '/api/v1/obligations/ob-1/register', body: { statusNote: 'Checked.' } }]);
  });

  it('reads a stale standing from its code, merges nothing and offers a reload', async () => {
    const sent = serve(WORKED, SPAN, () => ({ status: 409, data: { code: 'stale_write', detail: 'Someone changed this first. Reload and try again.' } }));
    renderPanel();
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    fireEvent.click(within(standingOf('Example Bank AB')).getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Status note'), { target: { value: 'Criteria agreed.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('Someone changed this entry while you were editing. Reload to see their version, then make your change again.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Status note')).toHaveValue('Criteria agreed.');
    const reads = sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reload' }));
    await waitFor(() => expect(sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length).toBeGreaterThan(reads));
  });

  it('holds what it is given beneath the companies: a standard\'s units', async () => {
    serve(WORKED);
    renderWith(
      <ObligationPositionPanel obligationId="ob-1">
        <span data-units-stand-in="" />
      </ObligationPositionPanel>,
      { permissions: ALL },
    );
    await screen.findByRole('heading', { level: 3, name: 'Example Bank AB' });
    const units = document.querySelector('[data-applicability-panel] [data-units-stand-in]');
    expect(units).not.toBeNull();
    // Separated from the last company like every other part: the wrapper draws the hairline the part's first-of-type reset would drop.
    expect(units?.parentElement?.className).toContain('border-t');
    expect(units?.parentElement?.hasAttribute('data-position-entity')).toBe(false);
  });

  it('says when the answers could not be loaded', async () => {
    serve(500);
    renderPanel();
    expect(await screen.findByText('Does it apply to us could not be loaded')).toBeInTheDocument();
  });
});
