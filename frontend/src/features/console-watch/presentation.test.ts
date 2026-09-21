import { describe, expect, it } from 'vitest';

import { t } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import { agentKeyState, isLive, presentAgentKey, type AgentKey } from './agent-keys';
import { authorityAndPublished, factProvenance, linkProvenance, type ConsoleChangeRow, type ObligationLink } from './change-facts';
import { linksWithout } from './change-facts-detail';
import { applyFilters, coverageSummary, presentSource, registryRows, sourceMeta, type RegistryRow, type Source, type SourceCoverage } from './sources';

// The edges the three console screens reach but their own tests do not drive:
// a record the library knows least about, and the states a key passes through
// on its own dates.

const NOW = new Date('2026-09-19T08:00:00Z');

const key = (over: Partial<AgentKey>): AgentKey => ({
  id: 'k',
  name: 'A key',
  keyPrefix: 'cw_live_a',
  scopes: ['library:read'],
  agentId: 'ag1',
  agent: { key: 'watch-sweeper', kind: 'agent', label: 'Watch sweeper v1' },
  createdAt: '2026-09-01T08:00:00Z',
  expiresAt: null,
  revokedAt: null,
  lastUsedAt: null,
  ...over,
});

describe('agent key state', () => {
  it('reads each state off the key\'s own dates', () => {
    expect(agentKeyState(key({ revokedAt: '2026-09-12T09:00:00Z' }), NOW)).toBe('revoked');
    expect(agentKeyState(key({ expiresAt: '2026-09-18T23:59:59Z' }), NOW)).toBe('expired');
    expect(agentKeyState(key({ expiresAt: '2026-10-01T23:59:59Z' }), NOW)).toBe('never_used');
    expect(agentKeyState(key({ lastUsedAt: '2026-09-19T06:00:00Z' }), NOW)).toBe('active');
  });

  it('counts a revoked and an expired key alike as stopped', () => {
    expect(isLive(key({}), NOW)).toBe(true);
    expect(isLive(key({ revokedAt: '2026-09-12T09:00:00Z' }), NOW)).toBe(false);
    expect(isLive(key({ expiresAt: '2026-09-18T23:59:59Z' }), NOW)).toBe(false);
  });

  it('names the agent when the key is bound to one, and shows the scopes either way', () => {
    const bound = presentAgentKey(key({}), t, NOW);
    expect(bound.map((p) => p.key)).toEqual(['state:never_used', 'agent:watch-sweeper', 'scope:library:read']);
    expect(bound.find((p) => p.key === 'agent:watch-sweeper')?.tone).toBe('brand');

    const unbound = presentAgentKey(key({ agent: null, agentId: null }), t, NOW);
    expect(unbound.map((p) => p.key)).toEqual(['state:never_used', 'scope:library:read']);
  });
});

const fact = (confidence: number | null, suggested: boolean) => ({ ref: { key: 'k', kind: null, label: 'K' }, confidence, suggested });

const changeRow = (over: Partial<ConsoleChangeRow>): ConsoleChangeRow =>
  ({
    id: 'c1',
    stableKey: 'k',
    title: 'A reform',
    changeType: fact(null, true),
    authorityLabel: 'ESMA',
    authorityId: null,
    publishedOn: null,
    publishedPrecision: null,
    status: 'active',
    flags: [],
    terms: [],
    obligations: [],
    unconfirmedCount: 1,
    firstSeenAt: '2026-09-16T06:02:00Z',
    ...over,
  }) as ConsoleChangeRow;

describe('change fact provenance', () => {
  it('says who put a fact forward, and with what confidence when one was recorded', () => {
    expect(factProvenance(fact(0.8624, true), t)).toBe('Suggested by the agent, confidence 0.86');
    expect(factProvenance(fact(null, true), t)).toBe('Suggested by the agent');
    expect(factProvenance(fact(0.5, false), t)).toBe('Confirmed for the library');
  });

  it('reads an obligation link the same way, off its confirmation flag', () => {
    const link = (confidence: number | null, confirmed: boolean) =>
      ({ obligationId: 'o1', title: 'A duty', instrumentShortName: 'LVM', refLabel: '9 kap.', origin: 'agent', confidence, confirmed }) as ObligationLink;
    expect(linkProvenance(link(0.41, false), t)).toBe('Suggested by the agent, confidence 0.41');
    expect(linkProvenance(link(null, true), t)).toBe('Confirmed for the library');
  });

  it('falls back to the day when a published date carries no precision, and to the authority alone when there is no date', () => {
    expect(authorityAndPublished(changeRow({ publishedOn: '2026-09-15' }), t, defaultFormatContext)).toBe('ESMA · Published 15 Sept 2026');
    expect(authorityAndPublished(changeRow({}), t, defaultFormatContext)).toBe('ESMA');
  });

  it('sends the set that remains when a link is dropped, never a delta', () => {
    const links = [
      { obligationId: 'o1', title: 'A', instrumentShortName: 'LVM', refLabel: '1 §', origin: 'agent', confidence: 0.9, confirmed: false },
      { obligationId: 'o2', title: 'B', instrumentShortName: 'LVM', refLabel: '2 §', origin: 'user', confidence: null, confirmed: true },
    ] as ObligationLink[];
    expect(linksWithout(links, 'o1')).toEqual([{ obligationId: 'o2', confidence: null }]);
  });
});

const source = (over: Partial<Source>): Source =>
  ({ id: 's', name: 'A source', url: null, kind: { key: 'authority_site', kind: null, label: 'Authority site' }, authorityId: null, checkFrequency: 'weekly', active: true, ...over }) as Source;

const coverageOf = (src: Source, over: Partial<SourceCoverage>): SourceCoverage =>
  ({ source: src, lastCheckedAt: null, lastStatus: 'never', lastError: null, overdue: false, ...over }) as SourceCoverage;

describe('source registry rows', () => {
  it('leaves a source the coverage read has not answered for standing on its own', () => {
    const unknown = source({ id: 's9', authorityId: 'a-gone' });
    const [row] = registryRows([unknown], [], []);
    expect(row!.coverage).toBeNull();
    // An authority the library no longer holds is the same as none: the row
    // still renders, it simply says less.
    expect(row!.authority).toBeNull();
    expect(presentSource(row!, t).map((p) => p.key)).toEqual(['kind:authority_site']);
    expect(sourceMeta(row!, t, defaultFormatContext)).toEqual(['Checked weekly', 'No check logged yet']);
  });

  it('counts a source with no coverage row in the registry but in neither number', () => {
    const fresh = source({ id: 's1' });
    const rows: RegistryRow[] = [
      { source: fresh, coverage: coverageOf(fresh, { lastCheckedAt: '2026-09-19T06:00:00Z', lastStatus: 'ok' }), authority: null },
      { source: source({ id: 's2' }), coverage: null, authority: null },
    ];
    expect(coverageSummary(rows, NOW)).toEqual({ total: 2, checked: 1, failing: 0 });
  });

  it('treats a stale source as failing even when its last check succeeded', () => {
    const stale = source({ id: 's3' });
    const rows: RegistryRow[] = [{ source: stale, coverage: coverageOf(stale, { lastCheckedAt: '2026-09-01T06:00:00Z', lastStatus: 'ok', overdue: true }), authority: null }];
    expect(coverageSummary(rows, NOW).failing).toBe(1);
    expect(applyFilters(rows, { jurisdiction: '', kind: '', failingOnly: true })).toHaveLength(1);
    // A row with no coverage at all is neither failing nor fresh, so the
    // failing filter leaves it out rather than guessing.
    expect(applyFilters([{ source: stale, coverage: null, authority: null }], { jurisdiction: '', kind: '', failingOnly: true })).toEqual([]);
  });
});
