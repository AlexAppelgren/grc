import type { components } from '@/types/api.generated';
import { api } from '@/shared/utils/api-client';

// The caller's own absence (TEN-04) and the people a delegate is picked from.
// Thin typed wrappers returning `.data` (playbook 6.1).

type Schemas = components['schemas'];
export type OutOfOffice = Schemas['MeOutOfOffice'];
export type OutOfOfficeBody = Schemas['MeOutOfOfficeBody'];
export type Person = Schemas['PersonRef'];

const OUT_OF_OFFICE = '/api/v1/me/out-of-office';

export async function getOutOfOffice(): Promise<OutOfOffice> {
  return (await api.get<OutOfOffice>(OUT_OF_OFFICE)).data;
}

/** Both fields to start an absence, both null to end it early. */
export async function putOutOfOffice(body: OutOfOfficeBody): Promise<OutOfOffice> {
  return (await api.put<OutOfOffice>(OUT_OF_OFFICE, body)).data;
}

export async function listPeople(): Promise<Person[]> {
  return (await api.get<Person[]>('/api/v1/reference/people')).data;
}
