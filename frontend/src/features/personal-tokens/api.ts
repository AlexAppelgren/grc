import type { PersonalTokenCreate, PersonalTokenCreated, PersonalTokensPage } from '@/features/personal-tokens/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1): a member's own personal
// access tokens (ACC-03). Minting asks for a passkey through the api client's
// step-up prompt; listing and revoking need a session alone.

const TOKENS = '/api/v1/me/tokens';

/** The route maximum: a person's own tokens fit one page. */
export const TOKENS_PAGE = 100;

export async function listMyTokens(): Promise<PersonalTokensPage> {
  return (await api.get<PersonalTokensPage>(TOKENS, { params: { limit: TOKENS_PAGE, offset: 0 } })).data;
}

export async function createMyToken(body: PersonalTokenCreate): Promise<PersonalTokenCreated> {
  return (await api.post<PersonalTokenCreated>(TOKENS, body)).data;
}

export async function revokeMyToken(tokenId: string): Promise<void> {
  await api.delete(`${TOKENS}/${encodeURIComponent(tokenId)}`);
}
