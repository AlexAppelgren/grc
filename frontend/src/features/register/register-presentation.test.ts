import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { presentApplicability, presentCompliance, presentComplianceHeader, presentGap, presentRisk, type ComplianceHeaderFacts } from './register-presentation';

const en = createT('en');
const sv = createT('sv');

describe('presentGap', () => {
  it('gap status, severity, source', () => {
    const pills = presentGap({
      status: { key: 'open', kind: 'open', label: 'Open' },
      severity: { key: 'high', kind: 'high', label: 'High' },
      source: { key: 'assessment', label: 'Impact assessment' },
    });
    expect(pills.map((p) => [p.label, p.tone, p.order])).toEqual([
      ['Open', 'negative', 10],
      ['High', 'negative', 20],
      ['Impact assessment', 'information', 30],
    ]);
  });

  it('tone follows the kind for every gap status and severity', () => {
    const statuses = (['open', 'remediating', 'risk_accepted', 'closed'] as const).map(
      (kind) => presentGap({ status: { key: kind, kind, label: 'x' }, severity: { key: 'low', kind: 'low', label: 'Low' } })[0]?.tone,
    );
    expect(statuses).toEqual(['negative', 'warning', 'information', 'positive']);
    const severities = (['high', 'medium', 'low'] as const).map(
      (kind) => presentGap({ status: { key: 'open', kind: 'open', label: 'Open' }, severity: { key: kind, kind, label: 'x' } })[1]?.tone,
    );
    expect(severities).toEqual(['negative', 'warning', 'information']);
  });

  it('omits a missing source', () => {
    expect(presentGap({ status: { key: 'closed', kind: 'closed', label: 'Closed' }, severity: { key: 'low', kind: 'low', label: 'Low' } })).toHaveLength(2);
  });
});

describe('presentApplicability', () => {
  it('names each fixed answer in en and sv, applies positive and the other two neutral', () => {
    const answers = ['applies', 'not_applicable', 'under_assessment'] as const;
    expect(answers.map((value) => [presentApplicability(value, en).label, presentApplicability(value, en).tone])).toEqual([
      ['Applies', 'positive'],
      ['Does not apply', 'information'],
      ['Not assessed', 'information'],
    ]);
    expect(answers.map((value) => presentApplicability(value, sv).label)).toEqual(['Gäller', 'Gäller inte', 'Inte bedömd']);
    expect(presentApplicability('applies', en).key).toBe('applicability:applies');
  });
});

describe('presentCompliance', () => {
  it('shows the bank label and takes the tone from the category, never the key', () => {
    const tones = (['compliant', 'partly', 'gap', 'not_assessed'] as const).map((kind) => presentCompliance({ key: `own_${kind}`, kind, label: 'Ours' }).tone);
    expect(tones).toEqual(['positive', 'warning', 'negative', 'information']);
    expect(presentCompliance({ key: 'partly_compliant', kind: 'partly', label: 'Delvis' })).toMatchObject({ key: 'compliance:partly_compliant', label: 'Delvis' });
  });

  it('reads a row with no category it knows as not assessed', () => {
    expect(presentCompliance({ key: 'odd', kind: null, label: 'Odd' }).tone).toBe('information');
  });
});

describe('presentRisk', () => {
  it('reads every risk as a neutral fact, whatever its place on the scale', () => {
    const tones = ['low', 'medium', 'high', 'critical', null].map((kind) => presentRisk({ key: kind ?? 'custom', kind, label: 'x' }).tone);
    expect(tones).toEqual(['information', 'information', 'information', 'information', 'information']);
    expect(presentRisk({ key: 'high', kind: null, label: 'Hög' })).toMatchObject({ key: 'risk:high', label: 'Hög' });
  });
});

describe('presentComplianceHeader', () => {
  const entity = (name: string, kind: string, applicability: ComplianceHeaderFacts['applicability'] = 'applies') => ({
    orgUnitName: name,
    applicability,
    complianceStatus: { key: kind, kind, label: kind },
  });

  it('names the weakest legal entity beside the worst-of status, in en and sv', () => {
    const facts: ComplianceHeaderFacts = {
      applicability: 'applies',
      complianceStatus: { key: 'partly', kind: 'partly', label: 'Partly compliant' },
      entities: [entity('Example Bank AB', 'compliant'), entity('Example Finans AB', 'partly')],
    };
    const header = presentComplianceHeader(facts, en);
    expect(header?.pill).toMatchObject({ label: 'Partly compliant', tone: 'warning' });
    expect(header?.weakest).toBe('at Example Finans AB, the weakest legal entity');
    expect(presentComplianceHeader(facts, sv)?.weakest).toBe('vid Example Finans AB, den svagaste juridiska personen');
  });

  it('names no entity for an obligation held as a whole or by one entity', () => {
    const whole: ComplianceHeaderFacts = { applicability: 'applies', complianceStatus: { key: 'gap', kind: 'gap', label: 'Gap' }, entities: [] };
    expect(presentComplianceHeader(whole, en)).toEqual({ pill: expect.objectContaining({ tone: 'negative' }), weakest: null });
    const one = { ...whole, entities: [entity('Example Bank AB', 'gap'), entity('Example Finans AB', 'compliant', 'not_applicable')] };
    expect(presentComplianceHeader(one, en)?.weakest).toBeNull();
  });

  it('shows no status where the obligation applies nowhere', () => {
    const facts: ComplianceHeaderFacts = {
      applicability: 'not_applicable',
      complianceStatus: { key: 'partly', kind: 'partly', label: 'Partly compliant' },
      entities: [entity('Example Bank AB', 'partly', 'not_applicable'), entity('Example Finans AB', 'gap', 'under_assessment')],
    };
    expect(presentComplianceHeader(facts, en)).toBeNull();
    expect(presentComplianceHeader({ ...facts, entities: [] }, en)).toBeNull();
  });
});
