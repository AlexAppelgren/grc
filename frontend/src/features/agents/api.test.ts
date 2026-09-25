import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as agents from './api';

// Each wrapper hits its route with its method, its body and its query, and
// returns `.data`. The paths are the contract's (backend/apps/agents/api.py).

const scope = { jurisdictions: ['se'], terms: [] };

describe('agents api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads and writes the platform definitions, their versions and settings in the console', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { ok: true } }));
    expect(await agents.listAgentDefinitions()).toEqual({ ok: true });
    await agents.getAgentDefinition('watch-sweeper');
    await agents.publishAgentVersion('watch-sweeper', { versionNo: 4, changeNote: 'Reads the consultation feed.' });
    await agents.retireAgentVersion('watch-sweeper', 2);
    await agents.getPlatformAgentSettings('watch-sweeper');
    await agents.updatePlatformAgentSettings('watch-sweeper', { cadence: 'daily', jurisdictions: ['eu', 'se'], monthlyBudget: '250.00' });
    await agents.createRetagRequest({ topic: 'Re-tag custody records' });

    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/agent-definitions'],
      ['get', '/api/v1/agent-definitions/watch-sweeper'],
      ['post', '/api/v1/agent-definitions/watch-sweeper/versions'],
      ['post', '/api/v1/agent-definitions/watch-sweeper/versions/2/retire'],
      ['get', '/api/v1/agent-definitions/watch-sweeper/settings'],
      ['put', '/api/v1/agent-definitions/watch-sweeper/settings'],
      ['post', '/api/v1/console/research-requests'],
    ]);
    expect(sent[0]?.params).toEqual({ limit: 100, offset: 0 });
    expect(sent[2]?.body).toEqual({ versionNo: 4, changeNote: 'Reads the consultation feed.' });
    expect(sent[5]?.body).toEqual({ cadence: 'daily', jurisdictions: ['eu', 'se'], monthlyBudget: '250.00' });
    expect(sent[6]?.body).toEqual({ topic: 'Re-tag custody records' });
  });

  it('puts a key into a path as one segment', async () => {
    const sent = installAdapter(() => ({ status: 200, data: {} }));
    await agents.getAgentDefinition('a/b');
    expect(sent[0]?.path).toBe('/api/v1/agent-definitions/a%2Fb');
  });

  it('reads the newest platform runs from the end of the oldest-first list', async () => {
    const sent = installAdapter((s, i) => (i === 0 ? { status: 200, data: { items: [{ id: 'r0' }], total: 130 } } : { status: 200, data: { items: [], total: 130 } }));
    await agents.listRecentPlatformRuns();
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/console/agent-runs', { limit: 1, offset: 0 }],
      ['/api/v1/console/agent-runs', { limit: 100, offset: 30 }],
    ]);
  });

  it('reads the whole list from the start while it fits on one page', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 12 } }));
    await agents.listRecentPlatformRuns();
    expect(sent[1]?.params).toEqual({ limit: 100, offset: 0 });
  });

  it("works a bank's own agents, their runs, its cap and its research requests", async () => {
    const sent = installAdapter(() => ({ status: 200, data: {} }));
    await agents.listPlatformWatch({ limit: 20 });
    await agents.listTenantAgents();
    await agents.createTenantAgent({ agent: 'source-checker', cadence: 'weekly', runWeekday: 1, runHour: 6, scope });
    await agents.updateTenantAgent('ta1', { enabled: false });
    await agents.runTenantAgentNow('ta1');
    await agents.pauseTenantAgent('ta1');
    await agents.resumeTenantAgent('ta1');
    await agents.listAgentRuns({ tenantAgentId: 'ta1', mine: true, limit: 20, offset: 0 });
    await agents.interruptAgentRun('r1');
    await agents.getAgentBudget();
    await agents.putAgentBudget({ monthlyCap: '100.00' });
    await agents.listResearchRequests({ offset: 20 });
    await agents.createResearchRequest({ kind: 'research_topic', tenantAgentId: 'ta1', topic: 'Custody', sourceId: null, url: null });
    await agents.getResearchRequest('rq1');

    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/agents/platform'],
      ['get', '/api/v1/agents'],
      ['post', '/api/v1/agents'],
      ['patch', '/api/v1/agents/ta1'],
      ['post', '/api/v1/agents/ta1/runs'],
      ['post', '/api/v1/agents/ta1/pause'],
      ['delete', '/api/v1/agents/ta1/pause'],
      ['get', '/api/v1/agent-runs'],
      ['post', '/api/v1/agent-runs/r1/interrupt'],
      ['get', '/api/v1/tenant/agent-budget'],
      ['put', '/api/v1/tenant/agent-budget'],
      ['get', '/api/v1/research-requests'],
      ['post', '/api/v1/research-requests'],
      ['get', '/api/v1/research-requests/rq1'],
    ]);
    expect(sent[0]?.params).toEqual({ limit: 20 });
    expect(sent[2]?.body).toEqual({ agent: 'source-checker', cadence: 'weekly', runWeekday: 1, runHour: 6, scope });
    expect(sent[3]?.body).toEqual({ enabled: false });
    expect(sent[7]?.params).toEqual({ tenantAgentId: 'ta1', mine: true, limit: 20, offset: 0 });
    expect(sent[10]?.body).toEqual({ monthlyCap: '100.00' });
    expect(sent[11]?.params).toEqual({ offset: 20 });
    expect(sent[12]?.body).toEqual({ kind: 'research_topic', tenantAgentId: 'ta1', topic: 'Custody', sourceId: null, url: null });
  });

  it('passes a refusal on to the caller as an error', async () => {
    installAdapter(() => ({ status: 403, data: { code: 'permission_denied', detail: 'No.' } }));
    await expect(agents.listAgentDefinitions()).rejects.toThrow();
  });
});
