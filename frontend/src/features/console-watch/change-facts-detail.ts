'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { listConsoleChanges, type ChangeFact, type ConsoleChangeRow, type ObligationLink } from '@/features/console-watch/change-facts';
import { api } from '@/shared/utils/api-client';
import type { components } from '@/types/api.generated';

// The write half of the Change facts card (WAT-03, WAT-04): reading one change
// in the console, correcting what an agent got wrong, and confirming what it
// got right for every bank. Confirming is a person's intervention in the
// agents' curation, so the route asks for a passkey and the api client runs
// that step-up (D-74); nobody confirms a fact they filed themselves.
//
// There is no console read of a single change. `GET /changes/{changeId}`
// answers the reader's own bank's case and footprint verdict beside the
// library record, so it belongs to a bank's session and answers 404 to a
// console one — which is right, because neither fact may appear here. The
// queue read is the console's own change read, so the page picks its change
// out of it; a change past that page reads as not found, and a `changeId`
// filter on `GET /console/changes` is what would close that (reported).

type Schemas = components['schemas'];

export type ChangePatch = Schemas['WatchChangePatch'];
export type ObligationLinkInput = Schemas['WatchObligationLinkInput'];
export type CurationConfirmInput = Schemas['WatchCurationConfirmInput'];

const CHANGES = '/api/v1/changes';

/** The route's own ceiling, so one read covers the deepest queue the console can show. */
export const CONSOLE_CHANGE_LOOKUP_PAGE = 100;

export async function correctChangeFacts(changeId: string, body: ChangePatch): Promise<Schemas['WatchChange']> {
  return (await api.patch<Schemas['WatchChange']>(`${CHANGES}/${changeId}`, body)).data;
}

export async function setObligationLinks(changeId: string, body: ObligationLinkInput[]): Promise<ObligationLink[]> {
  return (await api.put<ObligationLink[]>(`${CHANGES}/${changeId}/obligations`, body)).data;
}

export async function confirmCuration(changeId: string, body: CurationConfirmInput): Promise<ConsoleChangeRow> {
  return (await api.post<ConsoleChangeRow>(`${CHANGES}/${changeId}/confirmation`, body)).data;
}

export const consoleChangeDetailKeys = {
  lookup: ['console', 'changes', 'lookup'] as const,
  terms: ['console', 'taxonomy', 'terms'] as const,
};

/** Every change the console can reach, whether or not anything is left to confirm. */
function useConsoleChangeLookup(): UseQueryResult<ConsoleChangeRow[]> {
  return useQuery({
    queryKey: consoleChangeDetailKeys.lookup,
    queryFn: async () => (await listConsoleChanges({ confirmed: 'all', limit: CONSOLE_CHANGE_LOOKUP_PAGE, offset: 0 })).items,
  });
}

export interface ConsoleChangeResult {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  /** Null once the read succeeded and no change on it has this id. */
  change: ConsoleChangeRow | null;
  refetch: () => void;
}

export function useConsoleChange(changeId: string): ConsoleChangeResult {
  const lookup = useConsoleChangeLookup();
  return {
    isPending: lookup.isPending,
    isError: lookup.isError,
    error: lookup.error,
    change: lookup.data?.find((row) => row.id === changeId) ?? null,
    refetch: () => void lookup.refetch(),
  };
}

function useRereadChange(): () => Promise<void> {
  const queryClient = useQueryClient();
  // The corrected facts come back on the queue read the page is built from, so
  // the view follows a correction without a reload.
  return async () => {
    await queryClient.invalidateQueries({ queryKey: ['console', 'changes'] });
  };
}

export function useCorrectChangeFacts(changeId: string): UseMutationResult<Schemas['WatchChange'], unknown, ChangePatch> {
  const reread = useRereadChange();
  return useMutation({ mutationFn: (body) => correctChangeFacts(changeId, body), onSuccess: () => reread() });
}

export function useSetObligationLinks(changeId: string): UseMutationResult<ObligationLink[], unknown, ObligationLinkInput[]> {
  const reread = useRereadChange();
  return useMutation({ mutationFn: (body) => setObligationLinks(changeId, body), onSuccess: () => reread() });
}

/** The links that remain once one is dropped, as the route wants them: the whole set, never a delta. */
export function linksWithout(links: readonly ObligationLink[], obligationId: string): ObligationLinkInput[] {
  return links.filter((link) => link.obligationId !== obligationId).map((link) => ({ obligationId: link.obligationId, confidence: link.confidence }));
}

export function useConfirmCuration(changeId: string): UseMutationResult<ConsoleChangeRow, unknown, CurationConfirmInput> {
  const reread = useRereadChange();
  return useMutation({ mutationFn: (body) => confirmCuration(changeId, body), onSuccess: () => reread() });
}

/** Which facts one Confirm stands behind: one row of the card, or the rest of the change. */
export type ConfirmPart = 'type' | 'flags' | 'scope' | 'rest';

/**
 * The confirmation body for the facts still suggested in `part`, exactly as
 * they stand: the type by the key the reader saw, so a type corrected
 * meanwhile is refused rather than confirmed unread. A scope term goes by its
 * id, and one whose id is unknown is left out rather than guessed.
 */
export function confirmationOf(change: ConsoleChangeRow, part: ConfirmPart, termIdOf: (term: ChangeFact) => string | undefined): CurationConfirmInput {
  const takes = (which: ConfirmPart) => part === 'rest' || part === which;
  return {
    ...(takes('type') && change.changeType.suggested ? { changeType: change.changeType.ref.key } : {}),
    flags: takes('flags') ? change.flags.filter((flag) => flag.suggested).map((flag) => flag.ref.key) : [],
    termIds: takes('scope') ? change.terms.filter((term) => term.suggested).flatMap((term) => termIdOf(term) ?? []) : [],
    obligationIds: part === 'rest' ? change.obligations.filter((link) => !link.confirmed).map((link) => link.obligationId) : [],
  };
}

/**
 * A scope term's id, which the confirmation names it by and the change does
 * not carry: its fact answers `{key, kind, label}`, and a key is unique only
 * within its dimension. The term list answers every term with its id, key and
 * label in the reader's language, so a term is found by key and label
 * together, and a pair that matches two terms resolves to neither.
 */
export function useScopeTermIds(enabled: boolean): (term: ChangeFact) => string | undefined {
  const terms = useQuery({
    queryKey: consoleChangeDetailKeys.terms,
    queryFn: async () => (await api.get<Schemas['TaxonomyTermPage']>('/api/v1/taxonomy/terms', { params: { includeRetired: true } })).data.items,
    enabled,
    staleTime: 5 * 60_000,
  });
  const ids = new Map<string, string | null>();
  for (const term of terms.data ?? []) {
    const pair = `${term.key}\u0000${term.label}`;
    ids.set(pair, ids.has(pair) ? null : term.id);
  }
  return (term) => ids.get(`${term.ref.key}\u0000${term.ref.label}`) ?? undefined;
}
