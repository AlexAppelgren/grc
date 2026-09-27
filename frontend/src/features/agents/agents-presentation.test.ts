import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import {
  canRetire,
  definitionName,
  definitionStateOf,
  formatEuro,
  presentDefinition,
  presentJurisdictions,
  presentResearchRequest,
  presentRunState,
  presentTenantAgentState,
  presentVersion,
  runMinutes,
  runStateOf,
  tenantAgentStateOf,
  versionStateOf,
} from './agents-presentation';
import type { AgentDefinition, AgentVersion } from './types';

// Every pill's tone is the one design/system/pills-and-labels.md ("Chunk 11")
// gives the record's own facts; none is a choice a person makes.

const t = createT('en');
const sv = createT('sv');

const definition: AgentDefinition = {
  id: 'd1',
  key: 'watch-sweeper',
  description: 'Checks the sources.',
  currentVersion: 3,
  active: true,
  scope: 'platform',
  tenantConfigurable: false,
  publishedAt: '2026-09-21T07:12:00Z',
};

const version = (versionNo: number, retiredAt: string | null = null): AgentVersion => ({
  versionNo,
  model: 'large-eu',
  changeNote: 'First version.',
  publishedAt: '2026-09-02T06:00:00Z',
  publishedBy: { id: 'u1', name: 'Kari Nygaard' },
  retiredAt,
});

const tones = (pills: { label: string; tone: string }[]) => pills.map((p) => [p.label, p.tone]);

describe('agents presentation', () => {
  it('reads a run as done, running, stopped or failed, with a person’s stop winning', () => {
    expect(runStateOf({ status: 'succeeded', interruptedAt: null })).toBe('done');
    expect(runStateOf({ status: 'running', interruptedAt: null })).toBe('running');
    expect(runStateOf({ status: 'failed', interruptedAt: null })).toBe('failed');
    expect(runStateOf({ status: 'failed', interruptedAt: '2026-09-15T04:05:00Z' })).toBe('stopped');
    expect(tones([presentRunState({ status: 'succeeded', interruptedAt: null }, t)])).toEqual([['Done', 'positive']]);
    expect(tones([presentRunState({ status: 'running', interruptedAt: null }, t)])).toEqual([['Running', 'notice']]);
    expect(tones([presentRunState({ status: 'failed', interruptedAt: 'x' }, t)])).toEqual([['Stopped', 'warning']]);
    expect(tones([presentRunState({ status: 'failed', interruptedAt: null }, t)])).toEqual([['Failed', 'negative']]);
  });

  it("reads a bank's agent as on, paused or off, a pause winning over the switch", () => {
    expect(tenantAgentStateOf({ enabled: true, pausedAt: null })).toBe('on');
    expect(tenantAgentStateOf({ enabled: false, pausedAt: null })).toBe('off');
    expect(tenantAgentStateOf({ enabled: true, pausedAt: '2026-09-20T08:00:00Z' })).toBe('paused');
    expect(tones([presentTenantAgentState({ enabled: true, pausedAt: null }, t)])).toEqual([['On', 'positive']]);
    expect(tones([presentTenantAgentState({ enabled: true, pausedAt: 'x' }, t)])).toEqual([['Paused', 'warning']]);
    expect(tones([presentTenantAgentState({ enabled: false, pausedAt: null }, t)])).toEqual([['Off', 'information']]);
  });

  it('gives every research request status its pill', () => {
    const statuses = ['queued', 'running', 'done', 'failed', 'rejected', 'cancelled'] as const;
    expect(statuses.map((status) => tones([presentResearchRequest({ status }, t)])[0])).toEqual([
      ['Queued', 'information'],
      ['Running', 'notice'],
      ['Done', 'positive'],
      ['Failed', 'negative'],
      ['Rejected', 'information'],
      ['Cancelled', 'information'],
    ]);
  });

  it('shows a definition’s scope, version and state, and no version for a draft', () => {
    expect(tones(presentDefinition(definition, t))).toEqual([
      ['Platform', 'information'],
      ['Version 3', 'brand'],
      ['Active', 'positive'],
    ]);
    const draft = { ...definition, scope: 'tenant' as const, active: false, publishedAt: null };
    expect(definitionStateOf(draft)).toBe('draft');
    expect(tones(presentDefinition(draft, t))).toEqual([
      ['For banks', 'information'],
      ['Draft', 'information'],
    ]);
    expect(tones(presentDefinition(draft, sv))).toEqual([
      ['För banker', 'information'],
      ['Utkast', 'information'],
    ]);
  });

  it('marks the current and the retired version, and offers retire only on an earlier live one', () => {
    expect(versionStateOf(version(3), 3)).toBe('current');
    expect(versionStateOf(version(1, '2026-09-12T12:31:00Z'), 3)).toBe('retired');
    expect(versionStateOf(version(2), 3)).toBeNull();
    expect(tones(presentVersion(version(3), 3, t))).toEqual([['Current', 'positive']]);
    expect(tones(presentVersion(version(1, 'x'), 3, t))).toEqual([['Retired', 'information']]);
    expect(presentVersion(version(2), 3, t)).toEqual([]);
    expect(canRetire(version(2), 3)).toBe(true);
    expect(canRetire(version(3), 3)).toBe(false);
    expect(canRetire(version(1, 'x'), 3)).toBe(false);
  });

  it('gives a jurisdiction an agent sweeps the scope facet’s tone', () => {
    expect(tones(presentJurisdictions(['eu', 'se'], (key) => key.toUpperCase()))).toEqual([
      ['EU', 'brand'],
      ['SE', 'brand'],
    ]);
  });

  it('reads a cost in euro in the reader’s language, and nothing when none was reported', () => {
    expect(formatEuro('2.4', { locale: 'en' })).toBe('€2.40');
    expect(formatEuro('2.40', { locale: 'sv' })).toMatch(/^2,40\s€$/);
    expect(formatEuro(null, { locale: 'en' })).toBeNull();
  });

  it('counts whole minutes of a closed run, at least one, and none while it runs', () => {
    expect(runMinutes({ startedAt: '2026-09-25T04:00:00Z', finishedAt: '2026-09-25T04:16:10Z' })).toBe(16);
    expect(runMinutes({ startedAt: '2026-09-25T04:00:00Z', finishedAt: '2026-09-25T04:00:05Z' })).toBe(1);
    expect(runMinutes({ startedAt: '2026-09-25T04:00:00Z', finishedAt: null })).toBeNull();
  });

  it('names a definition by its key read as words', () => {
    expect(definitionName('watch-sweeper')).toBe('Watch sweeper');
    expect(definitionName('library_confirmer')).toBe('Library confirmer');
  });
});
