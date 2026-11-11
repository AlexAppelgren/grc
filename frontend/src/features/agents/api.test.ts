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

    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/agent-definitions'],
      ['get', '/api/v1/agent-definitions/watch-sweeper'],
      ['post', '/api/v1/agent-definitions/watch-sweeper/versions'],
      ['post', '/api/v1/agent-definitions/watch-sweeper/versions/2/retire'],
      ['get', '/api/v1/agent-definitions/watch-sweeper/settings'],
      ['put', '/api/v1/agent-definitions/watch-sweeper/settings'],
    ]);
    expect(sent[0]?.params).toEqual({ limit: 100, offset: 0 });
    expect(sent[2]?.body).toEqual({ versionNo: 4, changeNote: 'Reads the consultation feed.' });
    expect(sent[5]?.body).toEqual({ cadence: 'daily', jurisdictions: ['eu', 'se'], monthlyBudget: '250.00' });
  });

  it('puts a key into a path as one segment', async () => {
    const sent = installAdapter(() => ({ status: 200, data: {} }));
    await agents.getAgentDefinition('a/b');
    expect(sent[0]?.path).toBe('/api/v1/agent-definitions/a%2Fb');
  });

  // Review 2026-11-11, defect 2.5: the route answers newest first, so the newest
  // runs are its first page; reading the last page showed the oldest.
  it('reads the newest platform runs as the first page of the newest-first list', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [{ id: 'r-new' }, { id: 'r-old' }], total: 130 } }));
    expect((await agents.listRecentPlatformRuns()).items.map((run) => run.id)).toEqual(['r-new', 'r-old']);
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/console/agent-runs', { limit: 100, offset: 0 }]]);
  });

  it('reads one page whatever the total, never learning it first', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 12 } }));
    await agents.listRecentPlatformRuns();
    expect(sent).toHaveLength(1);
  });

  it("works a bank's own agents, their runs, its cap and its research requests", async () => {
    const sent = installAdapter(() => ({ status: 200, data: {} }));
    await agents.listPlatformWatch({ limit: 20 });
    await agents.listTenantAgents();
    await agents.createTenantAgent({ agent: 'source-checker', cadence: 'weekly', runWeekday: 1, runHour: 6, scope });
    await agents.updateTenantAgent('ta1', { enabled: false });
    await agents.runTenantAgentNow('ta1');
    await agents.interruptAgentRun('r1');
    await agents.getAgentBudget();
    await agents.putAgentBudget({ monthlyCap: '100.00' });
    await agents.listResearchRequests({ offset: 20 });
    await agents.createResearchRequest({ kind: 'research_topic', tenantAgentId: 'ta1', topic: 'Custody', sourceId: null, url: null });

    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/agents/platform'],
      ['get', '/api/v1/agents'],
      ['post', '/api/v1/agents'],
      ['patch', '/api/v1/agents/ta1'],
      ['post', '/api/v1/agents/ta1/runs'],
      ['post', '/api/v1/agent-runs/r1/interrupt'],
      ['get', '/api/v1/tenant/agent-budget'],
      ['put', '/api/v1/tenant/agent-budget'],
      ['get', '/api/v1/research-requests'],
      ['post', '/api/v1/research-requests'],
    ]);
    expect(sent[0]?.params).toEqual({ limit: 20 });
    expect(sent[2]?.body).toEqual({ agent: 'source-checker', cadence: 'weekly', runWeekday: 1, runHour: 6, scope });
    expect(sent[3]?.body).toEqual({ enabled: false });
    expect(sent[7]?.body).toEqual({ monthlyCap: '100.00' });
    expect(sent[8]?.params).toEqual({ offset: 20 });
    expect(sent[9]?.body).toEqual({ kind: 'research_topic', tenantAgentId: 'ta1', topic: 'Custody', sourceId: null, url: null });
  });

  it('passes a refusal on to the caller as an error', async () => {
    installAdapter(() => ({ status: 403, data: { code: 'permission_denied', detail: 'No.' } }));
    await expect(agents.listAgentDefinitions()).rejects.toThrow();
  });
});
