import type { components } from '@/types/api.generated';
import { api } from '@/shared/utils/api-client';

// "What applies" (REG-01, FP-05): the bank's legal entities, each with how many
// obligations the register offers for it and how its answers stand. A thin
// typed wrapper returning `.data` (playbook 6.1; backend/apps/register/api.py).

/** One legal entity with its offered count and the answers so far. */
export type ApplicabilityCompany = components['schemas']['RegisterApplicabilityCompany'];

/** Every active legal entity of the bank; a handful, so not paged. */
export async function listApplicabilityCompanies(): Promise<ApplicabilityCompany[]> {
  return (await api.get<ApplicabilityCompany[]>('/api/v1/applicability/companies')).data;
}
