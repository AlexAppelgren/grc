import { api } from '@/shared/utils/api-client';

import type { ParticipantInput, Participant, ParticipantPage, PersonRef, TeamPage } from './types';

// The participant calls (backend/apps/collab/api.py), on a register entry and
// on a case, and the people and team
// lists the picker reads (backend/apps/tenants/api.py), one thin typed
// wrapper per operation returning `.data` (playbook 6.1). Taking part grants
// nothing, so no call here asks for a step-up.

const V1 = '/api/v1';

const id = (value: string) => encodeURIComponent(value);
const participants = (obligationId: string) => `${V1}/obligations/${id(obligationId)}/participants`;
const caseParticipants = (changeId: string) => `${V1}/changes/${id(changeId)}/participants`;

/** A register entry or a case holds at most 50 participants unless configured otherwise, so one page of the maximum shows them all. */
export const PARTICIPANTS_PAGE = 100;

export async function listObligationParticipants(obligationId: string): Promise<ParticipantPage> {
  return (await api.get<ParticipantPage>(participants(obligationId), { params: { limit: PARTICIPANTS_PAGE } })).data;
}

export async function addObligationParticipant(obligationId: string, body: ParticipantInput): Promise<Participant> {
  return (await api.post<Participant>(participants(obligationId), body)).data;
}

export async function removeObligationParticipant(obligationId: string, participantId: string): Promise<void> {
  await api.delete(`${participants(obligationId)}/${id(participantId)}`);
}

// c9-fe-case-participants: the bank's case for a change, addressed by the change's id.
export async function listCaseParticipants(changeId: string): Promise<ParticipantPage> {
  return (await api.get<ParticipantPage>(caseParticipants(changeId), { params: { limit: PARTICIPANTS_PAGE } })).data;
}

export async function addCaseParticipant(changeId: string, body: ParticipantInput): Promise<Participant> {
  return (await api.post<Participant>(caseParticipants(changeId), body)).data;
}

export async function removeCaseParticipant(changeId: string, participantId: string): Promise<void> {
  await api.delete(`${caseParticipants(changeId)}/${id(participantId)}`);
}

/** The bank's active members who hold `permission`, as ids and names only. */
export async function listPeople(permission: string): Promise<PersonRef[]> {
  return (await api.get<PersonRef[]>(`${V1}/reference/people`, { params: { permission } })).data;
}

/** The bank's teams, active and retired; a bank keeps far fewer than a page of the maximum. */
export async function listTeams(): Promise<TeamPage> {
  return (await api.get<TeamPage>(`${V1}/tenant/teams`, { params: { limit: PARTICIPANTS_PAGE } })).data;
}
