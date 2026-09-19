import type {
  AssertionVerifyBody,
  CodeRequestBody,
  CodeVerifyBody,
  InvitationCodeVerifyBody,
  Me,
  MeUpdate,
  Passkey,
  PasskeyRegistrationOptions,
  PasskeyRequestOptions,
  PasskeyUpdate,
  RegisterVerifyBody,
  RegisterVerifyResponse,
  StepUpVerifyResponse,
  TokenResponse,
  UserSession,
} from '@/features/identity/types';
import { api } from '@/shared/utils/api-client';

// `nickname` in RegisterVerifyBody is optional: absent or blank, the server names
// the passkey from the device (ID-04, apps/identity/passkey_names.py).
export type { RegisterVerifyBody } from '@/features/identity/types';

// Thin typed wrappers returning `.data` (playbook 6.1). Paths are the
// identity app's routes under /api/v1 (CHUNK1_BRIEF.md). Bootstrap paths
// carry no bearer; the api client knows which ones.

const AUTH = '/api/v1/auth';
const ME = '/api/v1/me';

// The token rides in the body, never a path, so no request line holds it
// (security review F29).
export async function openInvitation(token: string): Promise<void> {
  await api.post(`${AUTH}/invitations/open`, { token });
}

// The invitation path: the link's token names the account, so no address is
// sent. The token rides in the body, never the path, so no access log holds it.
export async function verifyInvitationCode(body: InvitationCodeVerifyBody): Promise<TokenResponse> {
  return (await api.post<TokenResponse>(`${AUTH}/invitations/verify`, body)).data;
}

export async function requestCode(body: CodeRequestBody): Promise<void> {
  await api.post(`${AUTH}/code/request`, body);
}

export async function verifyCode(body: CodeVerifyBody): Promise<TokenResponse> {
  return (await api.post<TokenResponse>(`${AUTH}/code/verify`, body)).data;
}

export async function registerOptions(): Promise<PasskeyRegistrationOptions> {
  return (await api.post<PasskeyRegistrationOptions>(`${AUTH}/passkeys/register/options`, {})).data;
}

export async function registerVerify(body: RegisterVerifyBody): Promise<RegisterVerifyResponse> {
  return (await api.post<RegisterVerifyResponse>(`${AUTH}/passkeys/register/verify`, body)).data;
}

export async function authenticateOptions(): Promise<PasskeyRequestOptions> {
  return (await api.post<PasskeyRequestOptions>(`${AUTH}/passkeys/authenticate/options`, {})).data;
}

export async function authenticateVerify(body: AssertionVerifyBody): Promise<TokenResponse> {
  return (await api.post<TokenResponse>(`${AUTH}/passkeys/authenticate/verify`, body)).data;
}

export async function stepUpOptions(): Promise<PasskeyRequestOptions> {
  return (await api.post<PasskeyRequestOptions>(`${AUTH}/step-up/options`, {})).data;
}

export async function stepUpVerify(body: AssertionVerifyBody): Promise<StepUpVerifyResponse> {
  return (await api.post<StepUpVerifyResponse>(`${AUTH}/step-up/verify`, body)).data;
}

export async function getMe(): Promise<Me> {
  return (await api.get<Me>(ME)).data;
}

export async function updateMe(body: MeUpdate): Promise<Me> {
  return (await api.patch<Me>(ME, body)).data;
}

export async function listPasskeys(): Promise<Passkey[]> {
  return (await api.get<Passkey[]>(`${ME}/passkeys`)).data;
}

export async function renamePasskey(id: string, body: PasskeyUpdate): Promise<Passkey> {
  return (await api.patch<Passkey>(`${ME}/passkeys/${encodeURIComponent(id)}`, body)).data;
}

export async function removePasskey(id: string): Promise<void> {
  await api.delete(`${ME}/passkeys/${encodeURIComponent(id)}`);
}

export async function listSessions(): Promise<UserSession[]> {
  return (await api.get<UserSession[]>(`${ME}/sessions`)).data;
}

export async function revokeSession(id: string): Promise<void> {
  await api.delete(`${ME}/sessions/${encodeURIComponent(id)}`);
}
