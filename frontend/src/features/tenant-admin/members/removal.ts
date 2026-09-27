'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { adminKeys } from '@/features/tenant-admin/hooks';
import type { Owner } from '@/features/tenant-admin/teams/TeamPicker';
import { teamKeys } from '@/features/tenant-admin/teams/hooks';
import type { Translate } from '@/shared/i18n';
import type { components } from '@/types/api.generated';
import { api } from '@/shared/utils/api-client';
import { problemFrom } from '@/shared/utils/problem';

// Removing a member (TEN-05, TEN-S5, TEN-S9): what they hold by kind, a new
// owner per kind that moves, and the participations and teams that simply end.
// Nothing changes until the admin confirms; the removal is one step-up call
// and the server moves everything in one transaction or nothing at all.

type Schemas = components['schemas'];
export type OpenWork = Schemas['TenantMemberOpenWork'];
export type WorkKind = Schemas['TenantOpenWork']['kind'];
export type MovedKind = Schemas['TenantRemovalOwner']['kind'];
export type Owners = Partial<Record<MovedKind, Owner>>;

const MOVED: readonly WorkKind[] = ['register_entry', 'register_entity', 'gap', 'duty_occurrence', 'internal_item', 'case', 'action'];

const member = (userId: string) => `/api/v1/tenant/members/${encodeURIComponent(userId)}`;

export async function getOpenWork(userId: string): Promise<OpenWork> {
  return (await api.get<OpenWork>(`${member(userId)}/open-work`)).data;
}

export async function removeMember(userId: string, owners: Owners): Promise<void> {
  await api.post(`${member(userId)}/remove`, removalBody(owners));
}

/** The body: one owner per kind, as a team key or a person's id. */
export function removalBody(owners: Owners): Schemas['TenantMemberRemoveBody'] {
  return { owners: (Object.entries(owners) as [MovedKind, Owner][]).map(([kind, owner]) => ({ kind, ...owner })) };
}

export const isMoved = (kind: WorkKind): kind is MovedKind => MOVED.includes(kind);

/** The kinds that move to a new owner, with their counts, in the order the screen lists them. */
export function movedWork(work: OpenWork): { kind: MovedKind; count: number }[] {
  return MOVED.flatMap((kind) => work.items.filter((row) => row.kind === kind).map((row) => ({ kind: kind as MovedKind, count: row.count })));
}

/** How many items the member takes part in without owning them: those end. */
export const participationCount = (work: OpenWork): number => work.items.find((row) => row.kind === 'participation')?.count ?? 0;

/** The kinds a `reassignment_required` answer names, read from its code and errors, never its detail. */
export function kindsStillOwned(error: unknown): { kind: MovedKind; count: number }[] {
  const problem = problemFrom(error);
  if (problem?.code !== 'reassignment_required') return [];
  return (problem.errors ?? []).flatMap((entry) => {
    const record = typeof entry === 'object' && entry !== null ? (entry as Record<string, unknown>) : {};
    const kind = record.field as WorkKind;
    return typeof record.count === 'number' && isMoved(kind) ? [{ kind, count: record.count }] : [];
  });
}

/** A kind's name with its count, from the catalog. */
export function kindCount(kind: MovedKind, count: number, t: Translate): string {
  switch (kind) {
    case 'register_entry':
      return t('admin.members.removal.kind.registerEntry', { count });
    case 'register_entity':
      return t('admin.members.removal.kind.registerEntity', { count });
    case 'gap':
      return t('admin.members.removal.kind.gap', { count });
    case 'duty_occurrence':
      return t('admin.members.removal.kind.dutyOccurrence', { count });
    case 'internal_item':
      return t('admin.members.removal.kind.internalItem', { count });
    case 'case':
      return t('admin.members.removal.kind.case', { count });
    case 'action':
      return t('admin.members.removal.kind.action', { count });
  }
}

export function useOpenWork(userId: string, enabled: boolean): UseQueryResult<OpenWork> {
  return useQuery({ queryKey: [...adminKeys.members, userId, 'open-work'], queryFn: () => getOpenWork(userId), enabled, retry: false, gcTime: 0 });
}

export function useRemoveMember(): UseMutationResult<void, unknown, { userId: string; owners: Owners }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, owners }) => removeMember(userId, owners),
    // Marked stale, not refetched: the screen is leaving, and the removed member's own reads
    // (sessions, open work) would now answer 404. The member list refetches when it mounts.
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.members, refetchType: 'none' });
      await queryClient.invalidateQueries({ queryKey: teamKeys.all, refetchType: 'none' });
    },
  });
}
