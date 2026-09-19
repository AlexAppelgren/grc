import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { presentChangePending, presentObligation, presentScope, type ObligationFacts } from './obligation-presentation';

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
    expect(presentObligation(esma, 'header', t).map((p) => p.label)).toEqual(['ESMAGL', 'Securities', 'Guidance, comply or explain', 'Gap']);
  });

  it('omits a missing regime and never shows row-only pills', () => {
    const pills = presentObligation({ ...esma, regime: undefined }, 'header', t);
    expect(pills.map((p) => p.key)).toEqual(['instrument:esmagl', 'guidance', 'compliance:gap']);
  });
});

describe('presentScope', () => {
  it('one brand pill per term', () => {
    const scope = presentScope([{ key: 'bank', label: 'Bank' }, { key: 'fund', label: 'Fund company' }], false, t);
    expect(scope.pills.map((p) => [p.label, p.tone, p.order])).toEqual([
      ['Bank', 'brand', 0],
      ['Fund company', 'brand', 1],
    ]);
    expect(scope.plainText).toBeUndefined();
  });

  it('All services when every term is selected', () => {
    expect(presentScope([{ key: 'advice', label: 'Advice' }], true, t).pills).toEqual([{ key: 'all', label: 'All services', tone: 'brand', order: 0 }]);
  });

  it('plain text when empty, because empty means no restriction', () => {
    expect(presentScope([], false, t)).toEqual({ pills: [], plainText: 'Not client-specific' });
    expect(presentScope([], false, sv).plainText).toBe('Inte kundspecifik');
  });
});

describe('presentChangePending', () => {
  it('is a warning pill with the formatted date', () => {
    expect(presentChangePending('1 Oct 2026', t)).toEqual({ key: 'change-pending', label: 'Change pending: 1 Oct 2026', tone: 'warning', order: 0 });
  });
});
