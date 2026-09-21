import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import {
  canApprove,
  canWithdraw,
  diffFootprint,
  draftOf,
  historyLine,
  isRequester,
  narrowedGroups,
  pendingAdditions,
  pendingRemovals,
  pendingTermPill,
  presentFootprintDimension,
  presentRequestStatus,
  presentScope,
  previewLines,
  previewSummary,
  requestTitle,
  scopeGroups,
  termsOutside,
  toggleTerm,
} from './footprint-presentation';
import type { FootprintChangeRequest, FootprintDimension, FootprintPreview, TaxonomyTerm } from './types';

const t = createT('en');

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

describe('presentScope', () => {
  it('renders one brand pill per term, "Every service" when all are selected and plain text when empty', () => {
    expect(presentFootprintDimension(service, t)).toEqual({
      pills: [
        { key: 'term:advice', label: 'Advice', tone: 'brand', order: 0 },
        { key: 'term:custody', label: 'Custody', tone: 'brand', order: 1 },
      ],
      emptyText: null,
    });
    expect(presentScope(service.dimension, service.terms, true, t)).toEqual({ pills: [{ key: 'scope:all', label: 'Every service', tone: 'brand', order: 0 }], emptyText: null });
    expect(presentFootprintDimension(client, t)).toEqual({ pills: [], emptyText: 'Not restricted' });
  });
});

describe('request status and title', () => {
  it('maps the status kind to a tone and a phrase', () => {
    expect(presentRequestStatus('pending', t)).toEqual({ key: 'status:pending', label: 'Waiting for approval', tone: 'warning', order: 0 });
    expect(presentRequestStatus('approved', t)).toMatchObject({ label: 'Approved', tone: 'positive' });
    expect(presentRequestStatus('rejected', t)).toMatchObject({ label: 'Rejected', tone: 'information' });
    expect(presentRequestStatus('withdrawn', t)).toMatchObject({ label: 'Withdrawn', tone: 'information' });
  });

  it('titles the request from its terms', () => {
    expect(requestTitle(request(), t)).toBe('Switch off Advice');
    expect(requestTitle(request({ adds: [{ key: 'fund_company', kind: null, label: 'Fund company', dimension: 'legal_entity' }], removes: [] }), t)).toBe('Add Fund company');
    expect(requestTitle(request({ adds: [{ key: 'fund_company', kind: null, label: 'Fund company', dimension: 'legal_entity' }] }), t)).toBe('Add Fund company, switch off Advice');
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

  it('summarises the hidden side for the banner', () => {
    expect(previewSummary(preview, t)).toBe('Hides 4 obligations and 2 open cases.');
    expect(previewSummary({ hidden: { obligations: { count: 1, available: true } }, revealed: {} }, t)).toBe('Hides 1 obligation.');
    expect(previewSummary({ hidden: { obligations: { count: 0, available: false } }, revealed: {} }, t)).toBe('What it hides is not counted yet.');
    expect(previewSummary(undefined, t)).toBe('What it hides is not counted yet.');
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
  it('builds a draft from the stored footprint, toggles terms and diffs into adds and removes', () => {
    const draft = draftOf([service, client]);
    expect([...(draft.service_type ?? [])]).toEqual(['advice', 'custody']);
    expect(diffFootprint([service, client], draft)).toEqual({ adds: [], removes: [] });
    const next = toggleTerm(toggleTerm(draft, 'service_type', 'advice'), 'client_category', 'retail');
    expect(diffFootprint([service, client], next)).toEqual({ adds: [{ dimension: 'client_category', key: 'retail' }], removes: [{ dimension: 'service_type', key: 'advice' }] });
    expect(diffFootprint([service, client], toggleTerm(next, 'service_type', 'advice'))).toEqual({ adds: [{ dimension: 'client_category', key: 'retail' }], removes: [] });
    // A dimension the draft does not mention keeps its stored terms.
    expect(diffFootprint([service], {})).toEqual({ adds: [], removes: [] });
  });

  it('knows which terms a pending request switches off or on, and which terms sit outside the footprint', () => {
    expect([...pendingRemovals(request(), 'service_type')]).toEqual(['advice']);
    expect([...pendingRemovals(request(), 'regime')]).toEqual([]);
    expect([...pendingRemovals(null, 'service_type')]).toEqual([]);
    expect([...pendingAdditions(request({ adds: [{ key: 'retail', kind: null, label: 'Retail', dimension: 'client_category' }] }), 'client_category')]).toEqual(['retail']);
    const all: TaxonomyTerm[] = [
      { key: 'advice', kind: null, label: 'Advice', dimension: 'service_type' },
      { key: 'execution_only', kind: null, label: 'Execution only', dimension: 'service_type', active: true },
      { key: 'legacy', kind: null, label: 'Legacy', dimension: 'service_type', active: false },
      { key: 'retail', kind: null, label: 'Retail', dimension: 'client_category' },
    ];
    expect(termsOutside(all, service).map((term) => term.key)).toEqual(['execution_only']);
    expect(termsOutside(all, client).map((term) => term.key)).toEqual(['retail']);
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
  const allTerms: TaxonomyTerm[] = [
    { key: 'advice', kind: null, label: 'Advice', dimension: 'service_type' },
    { key: 'custody', kind: null, label: 'Custody', dimension: 'service_type' },
    { key: 'execution_only', kind: null, label: 'Execution only', dimension: 'service_type', active: true },
    { key: 'digital', kind: null, label: 'Digital', dimension: 'channel' },
    { key: 'retail', kind: null, label: 'Retail', dimension: 'client_category', active: false },
  ];

  it('keeps only dimensions that restrict the footprint and hold at least one term', () => {
    const groups = scopeGroups([service, client, channel, lifecycleStage, theme, termless], allTerms);
    expect(groups.map((g) => g.dimension.key)).toEqual(['service_type']);
    expect(groups[0]!.rows).toEqual([
      { term: allTerms[0], held: true },
      { term: allTerms[1], held: true },
      { term: allTerms[2], held: false },
    ]);
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
  it('names the decider, the request and the outcome', () => {
    const approved = request({ status: 'approved', decidedBy: { id: 'u4', name: 'Maria Ek' }, decidedAt: '2026-09-18T14:02:00Z' });
    expect(historyLine(approved, t, defaultFormatContext)).toEqual({ when: '18 Sept 2026', who: 'Maria Ek', text: 'approved "Switch off Advice" requested by Sara Lindqvist.' });
    const rejected = request({ status: 'rejected', decidedBy: { id: 'u4', name: 'Maria Ek' }, decidedAt: '2026-09-02T09:40:00Z', decisionNote: 'ISK tax reporting is ours.' });
    expect(historyLine(rejected, t, defaultFormatContext).text).toBe('rejected "Switch off Advice" requested by Sara Lindqvist: "ISK tax reporting is ours."');
    expect(historyLine(request({ status: 'withdrawn' }), t, defaultFormatContext)).toEqual({ when: '18 Sept 2026', who: 'Sara Lindqvist', text: 'withdrew "Switch off Advice".' });
    expect(historyLine(request(), t, defaultFormatContext).text).toBe('requested "Switch off Advice".');
  });
});
