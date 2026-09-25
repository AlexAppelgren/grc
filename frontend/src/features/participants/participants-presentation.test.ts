import { describe, expect, it } from 'vitest';

import type { Translate } from '@/shared/i18n';

import {
  addRefusals,
  CASE_PARTICIPANTS_EDIT_PERMISSION,
  caseAddRefusals,
  contributorTeams,
  isOwnRow,
  participantName,
  pickerOptions,
  presentContributorTeam,
  presentParticipant,
  rowAction,
} from './participants-presentation';
import type { Participant, Team } from './types';

// The panel offers Leave on your own row, Remove only with register.edit, and
// one picker over people and active teams; refusals read by code.

const t = ((key: string, params?: Record<string, unknown>) => (params === undefined ? key : `${key} ${JSON.stringify(params)}`)) as Translate;

const ANNA = { id: 'u-anna', name: 'Anna Nilsson' };
const ERIK = { id: 'u-erik', name: 'Erik Holm' };
const person: Participant = { id: 'p1', person: ERIK, team: null, addedBy: ANNA, addedAt: '2026-09-19T08:00:00Z' };
const team: Participant = { id: 'p2', person: null, team: { key: 'legal', kind: null, label: 'Legal' }, addedBy: ANNA, addedAt: '2026-09-18T08:00:00Z' };

function aTeam(key: string, label: string, active = true): Team {
  return { key, label, active, email: '', memberCount: 2, orgUnitId: null };
}

describe('participants presentation', () => {
  it('names a person or a team, and knows the reader’s own row', () => {
    expect(participantName(person)).toBe('Erik Holm');
    expect(participantName(team)).toBe('Legal');
    expect(isOwnRow(person, 'u-erik')).toBe(true);
    expect(isOwnRow(person, null)).toBe(false);
    expect(isOwnRow(team, 'u-erik')).toBe(false);
  });

  it('marks the own row with the You pill, in its slot’s tone', () => {
    expect(presentParticipant(person, 'u-erik', t)).toEqual([{ key: 'you', label: 'obligationParticipants.you', tone: 'positive', order: 0 }]);
    expect(presentParticipant(person, 'u-anna', t)).toEqual([]);
  });

  it('offers Leave on the own row whatever the role, and Remove only with register.edit', () => {
    expect(rowAction(person, 'u-erik', [])).toBe('leave');
    expect(rowAction(person, 'u-anna', ['register.edit'])).toBe('remove');
    expect(rowAction(team, 'u-anna', ['register.edit'])).toBe('remove');
    expect(rowAction(person, 'u-anna', ['register.read'])).toBeNull();
  });

  it('lists people and active teams in one picker, by name, narrowed by the query', () => {
    const options = pickerOptions([ERIK, ANNA], [aTeam('legal', 'Legal'), aTeam('old', 'Erstwhile desk', false), aTeam('retail', 'Retail compliance')], '');
    expect(options.map((o) => [o.kind, o.value])).toEqual([
      ['person', 'u-anna'],
      ['person', 'u-erik'],
      ['team', 'legal'],
      ['team', 'retail'],
    ]);
    expect(pickerOptions([ERIK, ANNA], [aTeam('retail', 'Retail compliance')], ' ER').map((o) => o.name)).toEqual(['Erik Holm']);
  });

  it('words each refusal of an add by its code', () => {
    const refusals = addRefusals('Erik Holm', t);
    expect(Object.keys(refusals).sort()).toEqual(['already_participant', 'participant_cannot_read', 'too_many_participants', 'unknown_key', 'unknown_member']);
    expect(refusals.already_participant).toBe('obligationParticipants.alreadyParticipant {"name":"Erik Holm"}');
  });

  it('on a case, offers Remove with cases.contribute and never with register.edit alone', () => {
    expect(rowAction(person, 'u-erik', [], CASE_PARTICIPANTS_EDIT_PERMISSION)).toBe('leave');
    expect(rowAction(person, 'u-anna', ['cases.contribute'], CASE_PARTICIPANTS_EDIT_PERMISSION)).toBe('remove');
    expect(rowAction(team, 'u-anna', ['register.edit', 'cases.read'], CASE_PARTICIPANTS_EDIT_PERMISSION)).toBeNull();
  });

  it('reads a case’s contributor teams as its team participants', () => {
    expect(contributorTeams([person, team]).map((row) => row.id)).toEqual(['p2']);
    expect(presentContributorTeam(team)).toEqual({ key: 'p2', label: 'Legal', tone: 'information', order: 0, outlined: true });
  });

  it('says a closed case takes no participants, by its code', () => {
    const refusals = caseAddRefusals('Erik Holm', t);
    expect(refusals.invalid_transition).toBe('caseParticipants.closed');
    expect(refusals.already_participant).toBe('caseParticipants.alreadyParticipant {"name":"Erik Holm"}');
  });
});
