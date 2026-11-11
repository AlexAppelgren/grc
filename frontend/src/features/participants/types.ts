import type { components } from '@/types/api.generated';

// Participants as the API sends them (openapi.json, generated; COL-04), and
// the two reference lists a participant is picked from.

type Schemas = components['schemas'];

export type Participant = Schemas['CollabParticipant'];
export type ParticipantPage = Schemas['CollabParticipantPage'];
/** Who to add; the record is the call's own subject. */
export type ParticipantInput = Omit<Schemas['CollabParticipantInput'], 'subjectType' | 'subjectId'>;
/** The record participants take part in: an obligation's register entry, or the case for a change. */
export type ParticipantSubject = { subjectType: Schemas['CollabParticipantInput']['subjectType']; subjectId: string };
export type PersonRef = Schemas['NamedRef'];
export type Team = Schemas['TenantTeam'];
