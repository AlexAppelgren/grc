import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import {
  changeSummary,
  isLibraryList,
  keyFromLabel,
  listLabel,
  nearDuplicateFrom,
  nearMatches,
  presentListSummary,
  presentVocabularyRow,
  presentVocabularyValue,
  usageText,
  valueTone,
} from './vocabulary-presentation';
import type { VocabularyListSummary, VocabularyRow } from './types';

// Tone comes from the list's slot or the row's kind, never from a label
// (design/system/pills-and-labels.md). The API row carries kind, tone and
// extra; a label-derived tone is a bug.

const t = createT('en');

function row(overrides: Partial<VocabularyRow> = {}): VocabularyRow {
  return {
    key: 'custody',
    kind: null,
    label: 'Custody',
    labels: { en: 'Custody', sv: 'Förvaring' },
    usageNote: '',
    sortOrder: 1,
    active: true,
    isSystem: false,
    isDefault: false,
    usageCount: 0,
    extra: {},
    ...overrides,
  };
}

function problem(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  return new AxiosError(`status ${status}`, String(status), config, undefined, { status, statusText: '', headers: {}, config, data });
}

describe('valueTone', () => {
  it('reads the slot: change type is notice, flag and library tag brand, tenant tag outlined information', () => {
    expect(valueTone('change_type', row({ kind: 'adopted' }))).toEqual({ tone: 'notice', outlined: false });
    expect(valueTone('flag', row())).toEqual({ tone: 'brand', outlined: false });
    expect(valueTone('library_tag', row())).toEqual({ tone: 'brand', outlined: false });
    expect(valueTone('taxonomy_term', row())).toEqual({ tone: 'brand', outlined: false });
    expect(valueTone('tenant_tag', row())).toEqual({ tone: 'information', outlined: true });
  });

  it('reads urgency from the row tone field and refuses anything outside the six tones', () => {
    expect(valueTone('urgency', row({ key: 'act_now', extra: { tone: 'negative', ordinal: 1 } })).tone).toBe('negative');
    expect(valueTone('urgency', row({ key: 'no_action', extra: { tone: 'positive' } })).tone).toBe('positive');
    // A label or a made-up colour never picks a tone.
    expect(valueTone('urgency', row({ key: 'act_now', label: 'Act now', extra: { tone: 'critical' } })).tone).toBe('information');
    expect(valueTone('urgency', row({ key: 'act_now', extra: {} })).tone).toBe('information');
  });

  it('reads compliance status from its category kind and case sub-statuses from theirs', () => {
    expect(valueTone('compliance_status', row({ kind: 'compliant' })).tone).toBe('positive');
    expect(valueTone('compliance_status', row({ kind: 'partly' })).tone).toBe('warning');
    expect(valueTone('compliance_status', row({ kind: 'gap' })).tone).toBe('negative');
    expect(valueTone('compliance_status', row({ kind: 'not_assessed' })).tone).toBe('information');
    expect(valueTone('compliance_status', row({ kind: null, label: 'Gap' })).tone).toBe('information');
    expect(valueTone('risk_rating', row({ kind: 'high' })).tone).toBe('negative');
    expect(valueTone('case_sub_status', row({ kind: 'assessing' })).tone).toBe('information');
  });

  it('is a neutral fact for every other list', () => {
    expect(valueTone('duty_type', row()).tone).toBe('information');
    expect(valueTone('something_new', row()).tone).toBe('information');
  });
});

describe('presentVocabularyValue and presentVocabularyRow', () => {
  it('renders the value as its real pill and the facts beside it', () => {
    const value = presentVocabularyValue('flag', row({ key: 'client_money', label: 'Client money' }));
    expect(value).toEqual({ key: 'value:client_money', label: 'Client money', tone: 'brand', order: 0, outlined: false });
    expect(presentVocabularyRow('tenant_tag', row({ isSystem: true, isDefault: true }), t).map((p) => [p.label, p.tone])).toEqual([
      ['System value', 'information'],
      ['Default', 'information'],
    ]);
    expect(presentVocabularyRow('tenant_tag', row({ active: false }), t).map((p) => p.label)).toEqual(['Retired']);
    expect(presentVocabularyRow('tenant_tag', row(), t)).toEqual([]);
  });
});

describe('usageText', () => {
  it('counts records or says the value is unused', () => {
    expect(usageText(0, t)).toBe('Not used yet');
    expect(usageText(1, t)).toBe('Used by 1 record');
    expect(usageText(4, t)).toBe('Used by 4 records');
  });
});

describe('nearMatches', () => {
  const rows = [row({ key: 'custody', label: 'Custody' }), row({ key: 'advice', label: 'Advice' }), row({ key: 'onboarding', label: 'Onboarding' }), row({ key: 'legacy', label: 'Legacy', active: false })];

  it('finds an exact match ignoring case and surrounding space', () => {
    const result = nearMatches('custody ', rows);
    expect(result.exact?.key).toBe('custody');
    expect(result.matches.map((r) => r.key)).toEqual(['custody']);
  });

  it('puts the near match first and never offers a retired value', () => {
    expect(nearMatches('Custdy', rows).matches.map((r) => r.key)).toEqual(['custody']);
    expect(nearMatches('custody svcs', rows).matches[0]?.key).toBe('custody');
    expect(nearMatches('leg', rows).matches).toEqual([]);
    expect(nearMatches('', rows).matches.map((r) => r.key)).toEqual(['custody', 'advice', 'onboarding']);
    expect(nearMatches('zzz', rows)).toEqual({ exact: null, matches: [] });
  });
});

describe('nearDuplicateFrom', () => {
  it('reads the candidates of a 422 near_duplicate from either shape the server may use', () => {
    expect(nearDuplicateFrom(problem(422, { code: 'near_duplicate', detail: 'x', candidates: [{ key: 'custody', label: 'Custody', similarity: 0.9 }] }))).toEqual([
      { key: 'custody', label: 'Custody', similarity: 0.9 },
    ]);
    expect(nearDuplicateFrom(problem(422, { code: 'near_duplicate', errors: [{ key: 'custody', label: 'Custody' }] }))).toEqual([{ key: 'custody', label: 'Custody' }]);
    expect(nearDuplicateFrom(problem(409, { code: 'near_duplicate', candidates: [{ key: 'custody', label: 'Custody' }] }))).toEqual([{ key: 'custody', label: 'Custody' }]);
    expect(nearDuplicateFrom(problem(422, { code: 'near_duplicate', candidates: [{ nope: 1 }, 'x'] }))).toEqual([]);
  });

  it('is null for any other error', () => {
    expect(nearDuplicateFrom(problem(422, { code: 'validation' }))).toBeNull();
    expect(nearDuplicateFrom(new Error('boom'))).toBeNull();
    expect(nearDuplicateFrom(null)).toBeNull();
  });
});

describe('listLabel and list summaries', () => {
  it('names the known lists from the catalog and humanises an unknown one', () => {
    expect(listLabel('tenant_tag', t)).toBe('Tenant tags');
    expect(listLabel('change_type', t)).toBe('Change types');
    expect(listLabel('flag', t)).toBe('Flags');
    expect(listLabel('pet_kind', t)).toBe('pet kind');
  });

  it('shows the tier and the pending suggestions on the list of lists', () => {
    const tenant: VocabularyListSummary = { list: 'tenant_tag', tier: 'tenant', kind: null, count: 6, retiredCount: 1, pendingSuggestions: 2 };
    const library: VocabularyListSummary = { list: 'flag', tier: 'library', kind: null, count: 6, retiredCount: 0 };
    expect(presentListSummary(tenant, t).map((p) => [p.label, p.tone, p.outlined ?? false])).toEqual([
      ['Tenant tag', 'information', true],
      ['2 suggestions', 'warning', false],
    ]);
    expect(presentListSummary(library, t).map((p) => [p.label, p.tone])).toEqual([['Flag', 'brand']]);
    expect(presentListSummary({ ...library, list: 'urgency' }, t).map((p) => [p.label, p.tone])).toEqual([['Urgency', 'information']]);
    expect(isLibraryList(tenant)).toBe(false);
    expect(isLibraryList(library)).toBe(true);
  });
});

describe('keyFromLabel and changeSummary', () => {
  it('slugs a label into a stable key', () => {
    expect(keyFromLabel('Client money')).toBe('client_money');
    expect(keyFromLabel('  Förvaring / Custody  ')).toBe('forvaring_custody');
    expect(keyFromLabel('T+1')).toBe('t_1');
    expect(keyFromLabel('***')).toBe('');
  });

  it('describes a proposal that came back from a library-list write', () => {
    expect(changeSummary({ title: 'Add "Client money"' }, t)).toBe('Add "Client money" is waiting for a library editor.');
  });
});
