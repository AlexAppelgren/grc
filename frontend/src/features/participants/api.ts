import { api, segment } from '@/shared/utils/api-client';

import type { ParticipantInput, Participant, ParticipantPage, ParticipantSubject } from './types';

// The participant calls (backend/apps/collab/api.py), one per verb for a
// register entry and a case alike, and the people and team
// lists the picker reads (backend/apps/tenants/api.py), one thin typed
// wrapper per operation returning `.data` (playbook 6.1). Taking part grants
// nothing, so no call here asks for a step-up.

const V1 = '/api/v1';

const PARTICIPANTS = `${V1}/participants`;

/** A register entry or a case holds at most 50 participants unless configured otherwise, so one page of the maximum shows them all. */
export const PARTICIPANTS_PAGE = 100;

export async function listParticipants(subject: ParticipantSubject): Promise<ParticipantPage> {
  return (await api.get<ParticipantPage>(PARTICIPANTS, { params: { ...subject, limit: PARTICIPANTS_PAGE } })).data;
}

export async function addParticipant(subject: ParticipantSubject, body: ParticipantInput): Promise<Participant> {
  return (await api.post<Participant>(PARTICIPANTS, { ...subject, ...body })).data;
}

/** Leaving one's own row and removing anyone else's are the same call; the server tells them apart. */
export async function removeParticipant(subject: ParticipantSubject, participantId: string): Promise<void> {
  await api.delete(`${PARTICIPANTS}/${segment(participantId)}`, { params: subject });
}

/** The bank's active members who hold `permission`, as ids and names only. */

/** The bank's teams, active and retired; a bank keeps far fewer than a page of the maximum. */
