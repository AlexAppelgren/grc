'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { api } from '@/shared/utils/api-client';
import type { components } from '@/types/api.generated';

// The reference data every picker and filter reads: the bank's people, its
// teams and the taxonomy's terms. One wrapper and one query key each, so the
// pickers of one page share one request and one cache entry, and a write that
// changes one of them refreshes every reader at once (playbook 6.1).

type Schemas = components['schemas'];

export type ReferencePerson = Schemas['PersonRef'];
export type ReferenceTeam = Schemas['TenantTeam'];
export type TermRow = Schemas['TaxonomyTermRow'];

const V1 = '/api/v1';

/** The server's maximum page: a bank's teams fit on it. */
const TEAMS_PAGE = 100;

export const referenceKeys = {
  /** Who may be picked, all members or only those holding `permission`. */
  people: (permission: string | null) => ['reference', 'people', permission] as const,
  teams: ['tenant', 'teams'] as const,
  terms: (dimension: string | null, includeRetired: boolean) => ['taxonomy', 'terms', dimension ?? 'all', includeRetired] as const,
};

export async function listPeople(permission: string | null = null): Promise<ReferencePerson[]> {
  return (await api.get<ReferencePerson[]>(`${V1}/reference/people`, { params: permission === null ? {} : { permission } })).data;
}

/** The bank's people; with a permission, only those who hold it. Read again after a minute. */
export function usePeople(permission: string | null = null, enabled = true): UseQueryResult<ReferencePerson[]> {
  return useQuery({ queryKey: referenceKeys.people(permission), queryFn: () => listPeople(permission), enabled, staleTime: 60_000 });
}

/** Every team, active and retired, in the list's order. */
export async function listTeams(): Promise<ReferenceTeam[]> {
  return (await api.get<Schemas['TenantTeamPage']>(`${V1}/tenant/teams`, { params: { limit: TEAMS_PAGE } })).data.items;
}

export function useTeams(enabled = true): UseQueryResult<ReferenceTeam[]> {
  return useQuery({ queryKey: referenceKeys.teams, queryFn: listTeams, enabled });
}

/** The terms as the route answers them, ids included: one read that every screen maps its own way. */
export async function listTermRows(dimension: string | null = null, includeRetired = false): Promise<TermRow[]> {
  const params = { ...(dimension === null ? {} : { dimension }), ...(includeRetired ? { includeRetired } : {}) };
  return (await api.get<Schemas['TaxonomyTermPage']>(`${V1}/taxonomy/terms`, { params })).data.items;
}

/** The query every terms reader spreads, with its own `select`. Terms change rarely, so they stay fresh for five minutes. */
export function termRowsQuery(dimension?: string, includeRetired = false) {
  return { queryKey: referenceKeys.terms(dimension ?? null, includeRetired), queryFn: () => listTermRows(dimension ?? null, includeRetired), staleTime: 5 * 60_000 };
}
