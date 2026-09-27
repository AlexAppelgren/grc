import type { components } from '@/types/api.generated';

// Participants as the API sends them (openapi.json, generated; COL-04), and
// the two reference lists a participant is picked from.

type Schemas = components['schemas'];

export type Participant = Schemas['CollabParticipant'];
export type ParticipantPage = Schemas['CollabParticipantPage'];
export type ParticipantInput = Schemas['CollabParticipantInput'];
export type PersonRef = Schemas['PersonRef'];
export type Team = Schemas['TenantTeam'];
export type TeamPage = Schemas['TenantTeamPage'];
