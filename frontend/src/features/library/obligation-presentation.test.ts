import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { outsideFootprintLabel, presentChangePending, presentObligation, presentScope, type ObligationFacts } from './obligation-presentation';

const t = createT('en');
const sv = createT('sv');

const lvm: ObligationFacts = {
  instrument: { key: 'lvm', label: 'LVM' },
  regime: { key: 'securities', label: 'Securities' },
  binding: true,
  applicability: { key: 'applies', kind: 'applies', label: 'Applies' },
  complianceStatus: { key: 'partly', kind: 'partly', label: 'Partly compliant' },
  openChangeCount: 2,
};

const esma: ObligationFacts = {
  instrument: { key: 'esmagl', label: 'ESMAGL' },
  regime: { key: 'securities', label: 'Securities' },
  binding: false,
  applicability: { key: 'applies', kind: 'applies', label: 'Applies' },
  complianceStatus: { key: 'gap', kind: 'gap', label: 'Gap' },
  changeWaitingForApproval: true,
  libraryTags: [{ key: 'appropriateness', label: 'Appropriateness' }],
  tenantTags: [{ key: 'digital', label: 'Digital investing' }],
};

describe('presentObligation row', () => {
  it('matches the card: instrument, applicability, compliance status, N open changes', () => {
    expect(presentObligation(lvm, 'row', t).map((p) => [p.label, p.tone, p.order])).toEqual([
      ['LVM', 'brand', 10],
      ['Applies', 'positive', 30],
      ['Partly compliant', 'warning', 40],
      ['2 open changes', 'notice', 60],
    ]);
  });

  it('matches the card: Guidance when not binding, Change waiting for approval, then tags', () => {
    expect(presentObligation(esma, 'row', t).map((p) => [p.label, p.tone, p.outlined ?? false])).toEqual([
      ['ESMAGL', 'brand', false],
      ['Guidance', 'information', false],
      ['Applies', 'positive', false],
      ['Gap', 'negative', false],
      ['Change waiting for approval', 'warning', false],
      ['Appropriateness', 'brand', false],
      ['Digital investing', 'information', true],
    ]);
  });

  it('plural and language come from the catalog', () => {
    expect(presentObligation({ ...lvm, openChangeCount: 1 }, 'row', t).at(-1)?.label).toBe('1 open change');
    expect(presentObligation({ ...lvm, openChangeCount: 3 }, 'row', sv).at(-1)?.label).toBe('3 öppna ändringar');
    expect(presentObligation({ ...lvm, openChangeCount: 0 }, 'row', t).map((p) => p.key)).not.toContain('open-changes');
  });

  it('compliance tone follows the kind', () => {
    const tones = (['compliant', 'partly', 'gap', 'not_assessed'] as const).map(
      (kind) => presentObligation({ instrument: lvm.instrument, binding: true, complianceStatus: { key: kind, kind, label: 'x' } }, 'row', t).at(-1)?.tone,
    );
    expect(tones).toEqual(['positive', 'warning', 'negative', 'information']);
  });

  it('applicability tone follows the kind', () => {
    const tones = (['applies', 'does_not_apply', 'not_assessed'] as const).map(
      (kind) => presentObligation({ instrument: lvm.instrument, binding: true, applicability: { key: kind, kind, label: 'x' } }, 'row', t).at(-1)?.tone,
    );
    expect(tones).toEqual(['positive', 'information', 'information']);
  });
});

describe('presentObligation header', () => {
  it('instrument, regime, binding level, compliance status', () => {
    expect(presentObligation(lvm, 'header', t).map((p) => [p.label, p.tone])).toEqual([
      ['LVM', 'brand'],
      ['Securities', 'information'],
      ['Binding', 'information'],
      ['Partly compliant', 'warning'],
    ]);
  });

  it('"Guidance, comply or explain" is a warning on the header, while the row keeps "Guidance" as information', () => {
    expect(presentObligation(esma, 'header', t).map((p) => [p.label, p.tone])).toEqual([
      ['ESMAGL', 'brand'],
      ['Securities', 'information'],
      ['Guidance, comply or explain', 'warning'],
      ['Gap', 'negative'],
    ]);
    expect(presentObligation(esma, 'row', t).find((p) => p.key === 'guidance')).toMatchObject({ label: 'Guidance', tone: 'information' });
    expect(presentObligation(esma, 'header', sv).find((p) => p.key === 'guidance')?.label).toBe('Vägledning, följ eller förklara');
  });

  it('omits a missing regime and never shows row-only pills', () => {
    const pills = presentObligation({ ...esma, regime: undefined }, 'header', t);
    expect(pills.map((p) => p.key)).toEqual(['instrument:esmagl', 'guidance', 'compliance:gap']);
  });
});

describe('presentScope', () => {
  const advice = { key: 'advice', label: 'Advice' };

  it('one brand pill per term', () => {
    const scope = presentScope({ dimension: 'legal_entity', terms: [{ key: 'bank', label: 'Bank' }, { key: 'fund', label: 'Fund company' }], allSelected: false }, t);
    expect(scope.pills.map((p) => [p.key, p.label, p.tone, p.order])).toEqual([
      ['scope:bank', 'Bank', 'brand', 0],
      ['scope:fund', 'Fund company', 'brand', 1],
    ]);
    expect(scope.plainText).toBeUndefined();
  });

  it('All services when every service is selected', () => {
    expect(presentScope({ dimension: 'service_type', terms: [advice], allSelected: true }, t)).toEqual({
      pills: [{ key: 'scope:all', label: 'All services', tone: 'brand', order: 0 }],
    });
    expect(presentScope({ dimension: 'service_type', terms: [advice], allSelected: true }, sv).pills[0]?.label).toBe('Alla tjänster');
  });

  it('a dimension with no designed "all" phrase lists its terms even when all are selected', () => {
    const scope = presentScope({ dimension: 'client_category', terms: [{ key: 'retail', label: 'Retail' }, { key: 'professional', label: 'Professional' }], allSelected: true }, t);
    expect(scope.pills.map((p) => p.label)).toEqual(['Retail', 'Professional']);
  });

  it('plain text when empty, because empty means no restriction, named for the dimension', () => {
    expect(presentScope({ dimension: 'client_category', terms: [], allSelected: false }, t)).toEqual({ pills: [], plainText: 'Not client-specific' });
    expect(presentScope({ dimension: 'client_category', terms: [], allSelected: false }, sv).plainText).toBe('Inte kundspecifik');
    const empty = (dimension: string) => presentScope({ dimension, terms: [], allSelected: false }, t).plainText;
    expect(
      ['regime', 'legal_entity', 'service_type', 'account_type', 'channel', 'lifecycle_stage', 'jurisdiction', 'licensed_activity', 'product_type'].map(empty),
    ).toEqual([
      'Not regime-specific',
      'Not entity-specific',
      'Not service-specific',
      'Not account-specific',
      'Not channel-specific',
      'Not stage-specific',
      'Not jurisdiction-specific',
      'Not activity-specific',
      'Not product-specific',
    ]);
    expect(presentScope({ dimension: 'channel', terms: [], allSelected: false }, sv).plainText).toBe('Inte kanalspecifik');
  });

  it('empty wins over allSelected, and a dimension the catalog does not know reads "Not specific"', () => {
    expect(presentScope({ dimension: 'service_type', terms: [], allSelected: true }, t)).toEqual({ pills: [], plainText: 'Not service-specific' });
    expect(presentScope({ dimension: 'theme', terms: [], allSelected: false }, t).plainText).toBe('Not specific');
    expect(presentScope({ dimension: 'theme', terms: [], allSelected: false }, sv).plainText).toBe('Inte specifik');
  });
});

describe('outsideFootprintLabel', () => {
  it('names the terms that put the row outside the footprint', () => {
    expect(outsideFootprintLabel([{ key: 'advice', label: 'Advice' }], t)).toBe('Outside your scope: Advice');
    expect(outsideFootprintLabel([{ key: 'advice', label: 'Advice' }, { key: 'custody', label: 'Custody' }], t)).toBe('Outside your scope: Advice, Custody');
    expect(outsideFootprintLabel([{ key: 'advice', label: 'Rådgivning' }], sv)).toBe('Utanför er omfattning: Rådgivning');
  });
});

describe('presentChangePending', () => {
  it('is a warning pill with the formatted date', () => {
    expect(presentChangePending('1 Oct 2026', t)).toEqual({ key: 'change-pending', label: 'Change pending: 1 Oct 2026', tone: 'warning', order: 0 });
  });
});
