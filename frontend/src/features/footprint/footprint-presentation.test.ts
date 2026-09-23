import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext, formatDateTime } from '@/shared/utils/format';

import {
  canApprove,
  canWithdraw,
  diffFootprint,
  draftAfter,
  draftOf,
  hidesSomething,
  historyLine,
  isRequester,
  narrowedGroups,
  pendingAdditions,
  pendingRemovals,
  pendingTermPill,
  presentRequestStatus,
  previewLines,
  previewSummary,
  requestTitle,
  scopeGroups,
  toggleTerm,
} from './footprint-presentation';
import type { FootprintChangeRequest, FootprintDimension, FootprintPreview, TaxonomyTerm } from './types';

const t = createT('en');
const sv = createT('sv');

const service: FootprintDimension = {
  dimension: { key: 'service_type', kind: 'scope', label: 'Service' },
  restrictsFootprint: true,
  terms: [
    { key: 'advice', kind: null, label: 'Advice' },
    { key: 'custody', kind: null, label: 'Custody' },
  ],
  allSelected: false,
};

const client: FootprintDimension = { dimension: { key: 'client_category', kind: 'scope', label: 'Client category' }, restrictsFootprint: true, terms: [], allSelected: false };

const preview: FootprintPreview = {
  hidden: { obligations: { count: 4, available: true }, cases: { count: 2, available: true } },
  revealed: { obligations: { count: 0, available: true }, cases: { count: 0, available: false } },
};

const retail = { key: 'retail', kind: null, label: 'Retail', dimension: 'client_category' };

function request(overrides: Partial<FootprintChangeRequest> = {}): FootprintChangeRequest {
  return {
    id: 'r1',
    status: 'pending',
    requestedBy: { id: 'u2', name: 'Sara Lindqvist' },
    requestedAt: '2026-09-18T12:00:00Z',
    adds: [],
    removes: [{ key: 'advice', kind: null, label: 'Advice', dimension: 'service_type' }],
    preview,
    decidedBy: null,
    decidedAt: null,
    decisionNote: '',
    version: 1,
    ...overrides,
  };
}

describe('request status and title', () => {
  it('maps the status kind to a tone and a phrase', () => {
    expect(presentRequestStatus('pending', t)).toEqual({ key: 'status:pending', label: 'Waiting for approval', tone: 'warning', order: 0 });
    expect(presentRequestStatus('approved', t)).toMatchObject({ label: 'Approved', tone: 'positive' });
    expect(presentRequestStatus('rejected', t)).toMatchObject({ label: 'Rejected', tone: 'information' });
    expect(presentRequestStatus('withdrawn', t)).toMatchObject({ label: 'Withdrawn', tone: 'information' });
  });

  it('titles the request from its terms, in plain words', () => {
    const fund = { key: 'fund_company', kind: null, label: 'Fund company', dimension: 'legal_entity' };
    expect(requestTitle(request(), t)).toBe('Remove Advice');
    expect(requestTitle(request({ adds: [fund], removes: [] }), t)).toBe('Add Fund company');
    expect(requestTitle(request({ adds: [fund] }), t)).toBe('Add Fund company, remove Advice');
    const distribution = { key: 'insurance_distribution', kind: null, label: 'Insurance distribution', dimension: 'service_type' };
    expect(requestTitle(request({ adds: [distribution, retail] }), t)).toBe('Add Insurance distribution and Retail, remove Advice');
    expect(requestTitle(request({ adds: [distribution, retail, fund], removes: [] }), t)).toBe('Add Insurance distribution, Retail and Fund company');
    expect(requestTitle(request({ adds: [{ ...retail, label: 'Icke-professionell' }], removes: [{ key: 'advice', kind: null, label: 'Rådgivning', dimension: 'service_type' }] }), sv)).toBe(
      'Lägg till Icke-professionell, ta bort Rådgivning',
    );
  });
});

describe('preview', () => {
  it('lists what is hidden and revealed, saying when a count is not known yet', () => {
    expect(previewLines(preview, t)).toEqual({
      hides: [
        { key: 'hides:obligations', text: '4 obligations', available: true },
        { key: 'hides:cases', text: '2 open cases', available: true },
      ],
      reveals: [
        { key: 'reveals:obligations', text: '0 obligations', available: true },
        { key: 'reveals:cases', text: 'Open cases: not counted yet', available: false },
      ],
    });
    expect(previewLines({ hidden: { widgets: { count: 1, available: true } }, revealed: {} }, t).hides).toEqual([{ key: 'hides:widgets', text: '1 widgets', available: true }]);
    expect(previewLines(null, t)).toEqual({ hides: [], reveals: [] });
  });

  it('summarises both sides in one sentence, leaving out what is not counted and a side that moves nothing', () => {
    const counted: FootprintPreview = {
      hidden: { obligations: { count: 2, available: true }, cases: { count: 0, available: false } },
      revealed: { obligations: { count: 1, available: true }, cases: { count: 0, available: false } },
    };
    expect(previewSummary(counted, t)).toBe('Hides 2 obligations and reveals 1 obligation.');
    expect(previewSummary(counted, sv)).toBe('Döljer 2 skyldigheter och visar 1 skyldighet.');
    // Nothing revealed: the sentence names only what is hidden, each kind joined once.
    expect(previewSummary(preview, t)).toBe('Hides 4 obligations and 2 open cases.');
    expect(previewSummary(preview, sv)).toBe('Döljer 4 skyldigheter och 2 öppna ärenden.');
    const three: FootprintPreview = { hidden: { obligations: { count: 1, available: true }, cases: { count: 2, available: true }, widgets: { count: 3, available: true } }, revealed: {} };
    expect(previewSummary(three, t)).toBe('Hides 1 obligation, 2 open cases and 3 widgets.');
    // Nothing hidden: only what appears.
    const widening: FootprintPreview = { hidden: { obligations: { count: 0, available: true } }, revealed: { obligations: { count: 3, available: true }, cases: { count: 0, available: false } } };
    expect(previewSummary(widening, t)).toBe('Reveals 3 obligations.');
    expect(previewSummary(widening, sv)).toBe('Visar 3 skyldigheter.');
    const still: FootprintPreview = { hidden: { obligations: { count: 0, available: true } }, revealed: { obligations: { count: 0, available: true } } };
    expect(previewSummary(still, t)).toBe('Hides nothing and reveals nothing.');
    expect(previewSummary(still, sv)).toBe('Döljer inget och visar inget.');
    expect(previewSummary({ hidden: { obligations: { count: 0, available: false } }, revealed: { obligations: { count: 0, available: false } } }, t)).toBe('What it hides is not counted yet.');
    expect(previewSummary(undefined, t)).toBe('What it hides is not counted yet.');
    // An answer that carries no revealed side is summarised from the side it does carry.
    expect(previewSummary({ hidden: { obligations: { count: 2, available: true } } } as unknown as FootprintPreview, t)).toBe('Hides 2 obligations.');
  });

  it('knows whether the counted part hides anything, never guessing at a count it does not have', () => {
    expect(hidesSomething(preview)).toBe(true);
    expect(hidesSomething({ hidden: { obligations: { count: 0, available: true } }, revealed: {} })).toBe(false);
    expect(hidesSomething({ hidden: { cases: { count: 3, available: false } }, revealed: {} })).toBe(false);
    expect(hidesSomething(undefined)).toBe(false);
  });
});

describe('who may do what', () => {
  it('lets a second person with footprint.approve approve, and only the requester withdraw', () => {
    const pending = request();
    expect(isRequester(pending, 'u2')).toBe(true);
    expect(isRequester(pending, 'u1')).toBe(false);
    expect(isRequester(pending, null)).toBe(false);
    expect(canApprove(pending, 'u1', ['footprint.approve'])).toBe(true);
    expect(canApprove(pending, 'u2', ['footprint.approve'])).toBe(false);
    expect(canApprove(pending, 'u1', ['footprint.request'])).toBe(false);
    expect(canApprove(request({ status: 'approved' }), 'u1', ['footprint.approve'])).toBe(false);
    expect(canWithdraw(pending, 'u2')).toBe(true);
    expect(canWithdraw(pending, 'u1')).toBe(false);
    expect(canWithdraw(request({ status: 'rejected' }), 'u2')).toBe(false);
  });
});

describe('draft and diff', () => {
  it('builds a draft from the stored scope, toggles terms and diffs into adds and removes', () => {
    const draft = draftOf([service, client]);
    expect([...(draft.service_type ?? [])]).toEqual(['advice', 'custody']);
    expect(diffFootprint([service, client], draft)).toEqual({ adds: [], removes: [] });
    const next = toggleTerm(toggleTerm(draft, 'service_type', 'advice'), 'client_category', 'retail');
    expect(diffFootprint([service, client], next)).toEqual({ adds: [{ dimension: 'client_category', key: 'retail' }], removes: [{ dimension: 'service_type', key: 'advice' }] });
    expect(diffFootprint([service, client], toggleTerm(next, 'service_type', 'advice'))).toEqual({ adds: [{ dimension: 'client_category', key: 'retail' }], removes: [] });
    // A dimension the draft does not mention keeps its stored terms.
    expect(diffFootprint([service], {})).toEqual({ adds: [], removes: [] });
  });

  it('knows which terms a pending request removes or adds', () => {
    expect([...pendingRemovals(request(), 'service_type')]).toEqual(['advice']);
    expect([...pendingRemovals(request(), 'regime')]).toEqual([]);
    expect([...pendingRemovals(null, 'service_type')]).toEqual([]);
    expect([...pendingAdditions(request({ adds: [retail] }), 'client_category')]).toEqual(['retail']);
  });

  it('builds the scope a request would leave, so the approver hears what it narrows', () => {
    const after = draftAfter([service, client], request({ adds: [retail] }));
    expect([...(after.service_type ?? [])]).toEqual(['custody']);
    expect([...(after.client_category ?? [])]).toEqual(['retail']);
    expect(narrowedGroups([service, client], after).map((d) => d.dimension.key)).toEqual(['client_category']);
    expect(narrowedGroups([service, client], draftAfter([service, client], request()))).toEqual([]);
    // A draft that does not mention an empty group leaves it empty, so it narrows nothing.
    expect(narrowedGroups([service, client], {})).toEqual([]);
  });
});

describe('scopeGroups, narrowedGroups and pendingTermPill', () => {
  const channel: FootprintDimension = { dimension: { key: 'channel', kind: 'classification', label: 'Channel' }, restrictsFootprint: false, terms: [{ key: 'digital', kind: null, label: 'Digital' }], allSelected: false };
  const lifecycleStage: FootprintDimension = {
    dimension: { key: 'lifecycle_stage', kind: 'classification', label: 'Lifecycle stage' },
    restrictsFootprint: false,
    terms: [{ key: 'pre_trade', kind: null, label: 'Pre-trade' }],
    allSelected: false,
  };
  const theme: FootprintDimension = { dimension: { key: 'theme', kind: 'classification', label: 'Theme' }, restrictsFootprint: false, terms: [{ key: 'aml', kind: null, label: 'AML' }], allSelected: false };
  const termless: FootprintDimension = { dimension: { key: 'jurisdiction', kind: 'scope', label: 'Jurisdiction' }, restrictsFootprint: true, terms: [], allSelected: false };
  const product: FootprintDimension = { dimension: { key: 'product_type', kind: 'scope', label: 'Product type' }, restrictsFootprint: true, terms: [], allSelected: false };
  const allTerms: TaxonomyTerm[] = [
    { key: 'advice', kind: null, label: 'Advice', dimension: 'service_type' },
    { key: 'custody', kind: null, label: 'Custody', dimension: 'service_type' },
    { key: 'execution_only', kind: null, label: 'Execution only', dimension: 'service_type', active: true },
    { key: 'legacy', kind: null, label: 'Legacy', dimension: 'service_type', active: false },
    { key: 'digital', kind: null, label: 'Digital', dimension: 'channel' },
    { key: 'retail', kind: null, label: 'Retail', dimension: 'client_category', active: true },
    { key: 'professional', kind: null, label: 'Professional', dimension: 'client_category' },
    { key: 'fund', kind: null, label: 'Fund', dimension: 'product_type', active: false },
  ];

  it('keeps the dimensions that restrict and have an active term, held or not, each listing every active term', () => {
    const groups = scopeGroups([service, client, channel, lifecycleStage, theme, termless, product], allTerms);
    // Channel, lifecycle stage and theme never restrict; jurisdiction and product type have no active term.
    expect(groups.map((g) => g.dimension.key)).toEqual(['service_type', 'client_category']);
    expect(groups[0]!.rows).toEqual([
      { term: allTerms[0], held: true },
      { term: allTerms[1], held: true },
      { term: allTerms[2], held: false },
    ]);
    // Nothing held: the group still shows, because an empty group is the unrestricted one.
    expect(groups[1]!.rows.map((row) => [row.term.key, row.held])).toEqual([
      ['retail', false],
      ['professional', false],
    ]);
  });

  it('keeps a held term that is no longer active, held and after the active ones, so its group still reads as filtering and it can be unticked', () => {
    // The seed takes a jurisdiction's term inactive with it, and the scope match ignores `active`.
    const sweden = { key: 'se', kind: null, label: 'Sweden' };
    const jurisdiction: FootprintDimension = { dimension: { key: 'jurisdiction', kind: 'scope', label: 'Jurisdiction' }, restrictsFootprint: true, terms: [sweden], allSelected: false };
    const legacy = { key: 'legacy', kind: null, label: 'Legacy' };
    const withLegacy: FootprintDimension = { ...service, terms: [...service.terms, legacy] };
    const groups = scopeGroups([withLegacy, jurisdiction], allTerms);
    expect(groups.map((g) => g.dimension.key)).toEqual(['service_type', 'jurisdiction']);
    expect(groups[0]!.rows.map((row) => [row.term.key, row.held])).toEqual([
      ['advice', true],
      ['custody', true],
      ['execution_only', false],
      ['legacy', true],
    ]);
    expect(groups[1]!.rows).toEqual([{ term: sweden, held: true }]);
  });

  it('detects narrowing (empty in the stored scope, non-empty in the draft) and not widening', () => {
    const draft = draftOf([service, client]);
    // Widening: adding to an already-restricting group is not a new narrowing.
    expect(narrowedGroups([service, client], toggleTerm(draft, 'service_type', 'execution_only'))).toEqual([]);
    // Narrowing: the first term ticked in an empty group.
    expect(narrowedGroups([service, client], toggleTerm(draft, 'client_category', 'retail')).map((d) => d.dimension.key)).toEqual(['client_category']);
    // A group already restricting, even if the draft empties it, was not narrowed by this draft.
    expect(narrowedGroups([service], {})).toEqual([]);
  });

  it('pends a term with the warning tone and the added/removed labels', () => {
    expect(pendingTermPill('add', t)).toEqual({ key: 'pending:add', label: 'Added when approved', tone: 'warning', order: 0 });
    expect(pendingTermPill('remove', t)).toEqual({ key: 'pending:remove', label: 'Removed when approved', tone: 'warning', order: 0 });
  });
});

describe('historyLine', () => {
  it('names the decider, the request and the outcome, with the time it was decided', () => {
    const approved = request({ status: 'approved', decidedBy: { id: 'u4', name: 'Maria Ek' }, decidedAt: '2026-09-18T14:02:00Z' });
    expect(historyLine(approved, t, defaultFormatContext)).toEqual({ when: formatDateTime('2026-09-18T14:02:00Z', defaultFormatContext), who: 'Maria Ek', text: 'approved "Remove Advice" requested by Sara Lindqvist.' });
    const rejected = request({ status: 'rejected', decidedBy: { id: 'u4', name: 'Maria Ek' }, decidedAt: '2026-09-02T09:40:00Z', decisionNote: 'ISK tax reporting is ours.' });
    expect(historyLine(rejected, t, defaultFormatContext).text).toBe('rejected "Remove Advice" requested by Sara Lindqvist: "ISK tax reporting is ours."');
    expect(historyLine(request({ status: 'withdrawn' }), t, defaultFormatContext)).toEqual({ when: formatDateTime('2026-09-18T12:00:00Z', defaultFormatContext), who: 'Sara Lindqvist', text: 'withdrew "Remove Advice".' });
    expect(historyLine(request(), t, defaultFormatContext).text).toBe('requested "Remove Advice".');
  });
});
