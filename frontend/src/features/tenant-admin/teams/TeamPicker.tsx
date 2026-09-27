'use client';

import { CheckGroup, CheckRow, Select } from '@/components/ui/Field';
import { StatusLine } from '@/components/ui/States';
import { usePeople } from '@/features/tenant-admin/organisation/hooks';
import type { Team } from '@/features/tenant-admin/teams/api';
import { useTeams } from '@/features/tenant-admin/teams/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// The team pickers the admin screens share (TEN-03): the teams a member is in,
// and a new owner that is a team or a person. Teams come as keys with labels
// from their rows; a retired team is offered only where it is already chosen.

/** An owner as one select value: a team by its key or a person by their id. */
export type Owner = { teamKey: string } | { userId: string };

export function ownerValue(owner: Owner | undefined): string {
  if (owner === undefined) return '';
  return 'teamKey' in owner ? `team:${owner.teamKey}` : `user:${owner.userId}`;
}

export function ownerOf(value: string): Owner | undefined {
  if (value.startsWith('team:')) return { teamKey: value.slice('team:'.length) };
  if (value.startsWith('user:')) return { userId: value.slice('user:'.length) };
  return undefined;
}

/** A new owner, a team or another member of the bank; `except` is the person who is leaving. */
export function OwnerSelect({ id, label, value, except, invalid, onChange }: { id: string; label: string; value: Owner | undefined; except: string; invalid?: boolean; onChange: (owner: Owner | undefined) => void }) {
  const t = useT();
  const teams = useTeams();
  const people = usePeople();
  return (
    <Select id={id} aria-label={label} value={ownerValue(value)} onChange={(e) => onChange(ownerOf(e.target.value))} aria-invalid={invalid === true} aria-busy={teams.isPending || people.isPending}>
      <option value="">{t('admin.teams.picker.choose')}</option>
      <optgroup label={t('admin.teams.picker.teams')}>
        {(teams.data ?? [])
          .filter((team) => team.active)
          .map((team) => (
            <option key={team.key} value={ownerValue({ teamKey: team.key })}>
              {team.label}
            </option>
          ))}
      </optgroup>
      <optgroup label={t('admin.teams.picker.people')}>
        {(people.data ?? [])
          .filter((person) => person.id !== except)
          .map((person) => (
            <option key={person.id} value={ownerValue({ userId: person.id })}>
              {person.name}
            </option>
          ))}
      </optgroup>
    </Select>
  );
}

/** The teams to offer a member: every active team, and a retired one they are already in. */
export function offeredTeams(teams: readonly Team[], chosen: readonly string[]): Team[] {
  return teams.filter((team) => team.active || chosen.includes(team.key));
}

/** The teams a member is in, one checkbox per team with its department beneath. */
export function TeamChecks({ value, departmentOf, onChange }: { value: readonly string[]; departmentOf: (orgUnitId: string | null) => string | undefined; onChange: (keys: string[]) => void }) {
  const t = useT();
  const teams = useTeams();
  const offered = offeredTeams(teams.data ?? [], value);
  return (
    <CheckGroup legend={t('admin.teams.member.legend')} hint={t('admin.teams.member.hint')}>
      {teams.isPending ? <StatusLine>{t('common.loading')}</StatusLine> : null}
      {teams.isSuccess && offered.length === 0 ? <StatusLine>{t('admin.teams.member.none')}</StatusLine> : null}
      {offered.map((team) => (
        <CheckRow
          key={team.key}
          id={`member-team-${team.key}`}
          label={team.label}
          hint={departmentOf(team.orgUnitId)}
          checked={value.includes(team.key)}
          onChange={(checked) => onChange(checked ? [...value, team.key] : value.filter((key) => key !== team.key))}
        />
      ))}
    </CheckGroup>
  );
}
