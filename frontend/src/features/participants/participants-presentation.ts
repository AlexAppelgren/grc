import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';

import type { Participant, PersonRef, Team } from './types';

// Who takes part in a record (COL-04; design/screens/tenant-obligation.html).
// Taking part grants nothing: these functions decide what the panel offers,
// and the server's answer, read by its `code`, is what holds.

/** Adding anyone and removing anyone else. Leaving one's own row needs nothing. */
export const PARTICIPANTS_EDIT_PERMISSION = 'register.edit';
/** Only members who can open the register are offered: anyone else would be told nothing. */
export const PARTICIPANT_READ_PERMISSION = 'register.read';

export function participantName(participant: Participant): string {
  return participant.person?.name ?? participant.team?.label ?? '';
}

export function isOwnRow(participant: Participant, meId: string | null): boolean {
  return meId !== null && participant.person?.id === meId;
}

/** The row's pills: "You" on the reader's own row, and nothing else. */
export function presentParticipant(participant: Participant, meId: string | null, t: Translate): PresentedPill[] {
  return isOwnRow(participant, meId) ? [{ key: 'you', label: t('obligationParticipants.you'), tone: slotTone.you, order: 0 }] : [];
}

/** What the row offers: Leave on one's own row, Remove on another's with the permission, else nothing. */
export function rowAction(
  participant: Participant,
  meId: string | null,
  permissions: readonly string[],
  editPermission: string = PARTICIPANTS_EDIT_PERMISSION,
): 'leave' | 'remove' | null {
  if (isOwnRow(participant, meId)) return 'leave';
  return permissions.includes(editPermission) ? 'remove' : null;
}

export interface PickerOption {
  kind: 'person' | 'team';
  /** The user id or the team key, which is what the add call sends. */
  value: string;
  name: string;
}

/** People and the bank's active teams in one list, by name, narrowed to the names holding `query`. */
export function pickerOptions(people: readonly PersonRef[], teams: readonly Team[], query: string): PickerOption[] {
  const needle = query.trim().toLocaleLowerCase();
  const options: PickerOption[] = [
    ...people.map((person): PickerOption => ({ kind: 'person', value: person.id, name: person.name })),
    ...teams.filter((team) => team.active).map((team): PickerOption => ({ kind: 'team', value: team.key, name: team.label })),
  ];
  return options.filter((option) => option.name.toLocaleLowerCase().includes(needle)).sort((a, b) => a.name.localeCompare(b.name));
}

/** The server's refusals of an add, in the panel's words, by `code`. */
export function addRefusals(name: string, t: Translate): Record<string, string> {
  return {
    already_participant: t('obligationParticipants.alreadyParticipant', { name }),
    participant_cannot_read: t('obligationParticipants.cannotRead', { name }),
    too_many_participants: t('obligationParticipants.tooMany'),
    unknown_member: t('obligationParticipants.unknownMember'),
    unknown_key: t('obligationParticipants.unknownTeam'),
  };
}

// ---------------------------------------------------------------------------
// c9-fe-case-participants: the bank's case for a change (COL-04, CAS-03)
// ---------------------------------------------------------------------------

/** Adding anyone to a case, removing anyone else and changing its contributor teams. */
export const CASE_PARTICIPANTS_EDIT_PERMISSION = 'cases.contribute';
/** Only members who can open cases are offered. */
export const CASE_PARTICIPANT_READ_PERMISSION = 'cases.read';

/** The case's team participants, which are its assessment's contributor teams (D-20). */
export function contributorTeams(participants: readonly Participant[]): Participant[] {
  return participants.filter((participant) => participant.team !== null);
}

/** A contributor team as its pill: a row of the bank's own team list, so outlined in the tenant tag's tone. */
export function presentContributorTeam(participant: Participant): PresentedPill {
  return { key: participant.id, label: participantName(participant), tone: slotTone.tenantTag, order: 0, outlined: true };
}

/** The server's refusals of a case add, in the case's words, by `code`. */
export function caseAddRefusals(name: string, t: Translate): Record<string, string> {
  return {
    already_participant: t('caseParticipants.alreadyParticipant', { name }),
    participant_cannot_read: t('caseParticipants.cannotRead', { name }),
    too_many_participants: t('caseParticipants.tooMany'),
    invalid_transition: t('caseParticipants.closed'),
    unknown_member: t('obligationParticipants.unknownMember'),
    unknown_key: t('obligationParticipants.unknownTeam'),
  };
}
