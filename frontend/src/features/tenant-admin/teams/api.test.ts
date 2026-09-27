import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetApiForTests } from '@/shared/testing/api-adapter';
import { api, pathOf, tokenStore } from '@/shared/utils/api-client';

import * as teams from './api';
import { offeredTeams, ownerOf, ownerValue } from './TeamPicker';

// Each wrapper hits its route with its method and body; a rename sends the
// version it was read at as If-Match. An owner is one select value, a team or
// a person, and a retired team is offered only to someone already in it.

interface Call {
  method: string;
  path: string;
  body: unknown;
  ifMatch: unknown;
}

function server(data: unknown): Call[] {
  const calls: Call[] = [];
  const adapter: AxiosAdapter = async (config) => {
    calls.push({
      method: config.method ?? 'get',
      path: pathOf(config),
      body: typeof config.data === 'string' ? JSON.parse(config.data) : null,
      ifMatch: config.headers.get('If-Match') ?? null,
    });
    return { data, status: 200, statusText: '200', headers: {}, config: config as InternalAxiosRequestConfig };
  };
  api.defaults.adapter = adapter;
  return calls;
}

const team = { key: 'cards', label: 'Cards', email: '', active: true, memberCount: 3, orgUnitId: null };

describe('teams api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the teams in one page and adds one to the team list', async () => {
    const calls = server({ items: [team], total: 1 });
    expect(await teams.listTeams()).toEqual([team]);
    await teams.createTeam(teams.teamLabels(' Cards ', ''));
    expect(calls.map(({ method, path, body }) => [method, path, body])).toEqual([
      ['get', '/api/v1/tenant/teams', null],
      ['post', '/api/v1/vocab/team', { labels: { en: 'Cards' } }],
    ]);
  });

  it('renames a team with its version as If-Match', async () => {
    const calls = server({});
    await teams.renameTeam('cards', teams.teamLabels('Cards', 'Kort'), 4);
    expect(calls[0]).toEqual({ method: 'patch', path: '/api/v1/vocab/team/cards', body: { labels: { en: 'Cards', sv: 'Kort' } }, ifMatch: '"4"' });
  });

  it("sets a member's whole set of teams", async () => {
    const calls = server({ userId: 'u 1', teams: ['cards'] });
    await teams.setMemberTeams('u 1', ['cards']);
    expect(calls[0]).toMatchObject({ method: 'put', path: '/api/v1/tenant/members/u%201/teams', body: { teams: ['cards'] } });
  });
});

describe('the team pickers', () => {
  it('reads an owner back from its select value, and nothing from the placeholder', () => {
    for (const owner of [{ teamKey: 'cards' }, { userId: 'u-sara' }]) expect(ownerOf(ownerValue(owner))).toEqual(owner);
    expect(ownerValue(undefined)).toBe('');
    expect(ownerOf('')).toBeUndefined();
  });

  it('offers a retired team only to a member already in it', () => {
    const retired = { ...team, key: 'old_desk', active: false };
    expect(offeredTeams([team, retired], []).map((t) => t.key)).toEqual(['cards']);
    expect(offeredTeams([team, retired], ['old_desk']).map((t) => t.key)).toEqual(['cards', 'old_desk']);
  });
});
