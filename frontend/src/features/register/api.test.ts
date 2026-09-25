import type { AxiosAdapter } from 'axios';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import * as register from './api';

// Each wrapper hits its route with its method, body and query, returns
// `.data`, and a write to a versioned row carries the version as If-Match.

function record() {
  const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: { ok: s.path } }));
  const inner = api.defaults.adapter as AxiosAdapter;
  const ifMatch: (string | null)[] = [];
  api.defaults.adapter = (config) => {
    ifMatch.push((config.headers.get('If-Match') as string | undefined) ?? null);
    return inner(config);
  };
  return { sent, ifMatch };
}

describe('register api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads every register list and record on its own route', async () => {
    const { sent } = record();
    expect(await register.getRegisterEntry('ob 1')).toEqual({ ok: '/api/v1/obligations/ob%201/register' });
    await register.listObligationGaps('ob1', { limit: 50 });
    await register.listGaps({ status: 'open', entity: 'e1' }, { offset: 20 });
    await register.listAssessments('ob1');
    await register.getInterpretation('ob1');
    await register.listInternalLinks('ob1');
    await register.listInternalItems('reconc');
    await register.listUnits('ob1');
    await register.listUnits('ob1', 'e1', { limit: 100 });
    await register.getStatementOfApplicability('ob1', 'e1');
    await register.listDuties('ob1');
    expect(sent.map((s) => [s.method, s.path, s.params])).toEqual([
      ['get', '/api/v1/obligations/ob%201/register', null],
      ['get', '/api/v1/obligations/ob1/gaps', { limit: 50 }],
      ['get', '/api/v1/gaps', { status: 'open', entity: 'e1', offset: 20 }],
      ['get', '/api/v1/obligations/ob1/assessments', {}],
      ['get', '/api/v1/obligations/ob1/interpretation', null],
      ['get', '/api/v1/obligations/ob1/internal-links', {}],
      ['get', '/api/v1/internal-items', { q: 'reconc' }],
      ['get', '/api/v1/obligations/ob1/units', {}],
      ['get', '/api/v1/obligations/ob1/units', { entity: 'e1', limit: 100 }],
      ['get', '/api/v1/obligations/ob1/statement-of-applicability', { entity: 'e1' }],
      ['get', '/api/v1/obligations/ob1/duties', {}],
    ]);
  });

  it('sends If-Match with the version on every versioned write', async () => {
    const { sent, ifMatch } = record();
    await register.updateRegister('ob1', { statusNote: 'Daily' }, 7);
    await register.updateRegisterEntity('ob1', 'e1', { complianceStatus: 'compliant' }, 0);
    await register.setApplicability('ob1', { applicability: 'applies', reason: 'Licensed' }, 3);
    await register.updateGap('g1', { targetDate: '2026-12-31' }, 2);
    await register.saveInterpretation('ob1', { text: 'Research covers analysts.' }, 4);
    await register.updateUnit('u1', { title: 'Policies' }, 5);
    await register.removeUnit('u1', 6);
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['patch', '/api/v1/obligations/ob1/register', { statusNote: 'Daily' }],
      ['patch', '/api/v1/obligations/ob1/register/entities/e1', { complianceStatus: 'compliant' }],
      ['put', '/api/v1/obligations/ob1/applicability', { applicability: 'applies', reason: 'Licensed' }],
      ['patch', '/api/v1/gaps/g1', { targetDate: '2026-12-31' }],
      ['put', '/api/v1/obligations/ob1/interpretation', { text: 'Research covers analysts.' }],
      ['patch', '/api/v1/units/u1', { title: 'Policies' }],
      ['delete', '/api/v1/units/u1', null],
    ]);
    expect(ifMatch).toEqual(['"7"', '"0"', '"3"', '"2"', '"4"', '"5"', '"6"']);
  });

  it('sends the unversioned writes without If-Match', async () => {
    const { sent, ifMatch } = record();
    const rows = [{ obligationId: 'ob1', applicability: 'not_applicable' as const, reason: 'No client money' }];
    await register.setApplicabilityMany({ rows });
    await register.createGap('ob1', { severity: 'high', source: 'assessment', title: 'No yearly review' });
    await register.requestRiskAcceptance('g1', { reason: 'cost_exceeds_benefit' });
    await register.approveRiskAcceptance('g1');
    await register.reopenGap('g1');
    await register.addInternalLink('ob1', { kind: 'policy', label: 'Client asset policy' });
    await register.removeInternalLink('l1');
    await register.createUnit('ob1', { orgUnitId: 'e1', reference: 'A.5.1', title: 'Policies' });
    await register.pasteUnits('ob1', { orgUnitId: 'e1', lines: [{ reference: 'A.5.1', title: 'Policies' }], dryRun: true });
    await register.completeDutyOccurrence('o1', { note: 'Filed' });
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['post', '/api/v1/applicability'],
      ['post', '/api/v1/obligations/ob1/gaps'],
      ['post', '/api/v1/gaps/g1/accept-risk'],
      ['post', '/api/v1/gaps/g1/accept-risk/approve'],
      ['post', '/api/v1/gaps/g1/reopen'],
      ['post', '/api/v1/obligations/ob1/internal-links'],
      ['delete', '/api/v1/internal-links/l1'],
      ['post', '/api/v1/obligations/ob1/units'],
      ['post', '/api/v1/obligations/ob1/units/paste'],
      ['post', '/api/v1/duty-occurrences/o1/complete'],
    ]);
    expect(sent[0]?.body).toEqual({ rows });
    expect(ifMatch.every((value) => value === null)).toBe(true);
  });
});
