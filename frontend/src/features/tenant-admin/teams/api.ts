import type { Member, Page } from '@/features/tenant-admin/types';
import type { components } from '@/types/api.generated';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1) for the bank's teams
// (TEN-03). A team is a row of the bank's own `team` list, so adding and
// renaming one goes through the list's own route at /vocab/team under
// vocab.manage; who is in a team is set on the member under members.manage.

export type Team = components['schemas']['TenantTeam'];

const TENANT = '/api/v1/tenant';
const TEAM_LIST = '/api/v1/vocab/team';

const id = (value: string) => encodeURIComponent(value);

/** A team's name per content language; Swedish only when one was given. */
export function teamLabels(en: string, sv: string): Record<string, string> {
  return sv.trim() === '' ? { en: en.trim() } : { en: en.trim(), sv: sv.trim() };
}

/** Every team, active and retired, in the list's order: one page at the server's maximum. */
export async function listTeams(): Promise<Team[]> {
  return (await api.get<Page<Team>>(`${TENANT}/teams`, { params: { limit: 100 } })).data.items;
}

export async function createTeam(labels: Record<string, string>): Promise<void> {
  await api.post(TEAM_LIST, { labels });
}

/** A new name, sent with the version the row was read at, so a rename made in between is refused with stale_write. */
export async function renameTeam(key: string, labels: Record<string, string>, version: number | undefined): Promise<void> {
  await api.patch(`${TEAM_LIST}/${id(key)}`, { labels }, version === undefined ? {} : { version });
}

/** The whole set of teams a member is in; the answer is the member as they now stand. */
export async function setMemberTeams(userId: string, teams: readonly string[]): Promise<Member> {
  return (await api.put<Member>(`${TENANT}/members/${id(userId)}/teams`, { teams })).data;
}
