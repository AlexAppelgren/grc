'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as identity from '@/features/identity/api';
import type { Me, Passkey, RegisterVerifyResponse, StepUpVerifyResponse, TokenResponse, UserSession } from '@/features/identity/types';
import { defaultLocale, isLocale, type Locale } from '@/shared/i18n';
import { ensureColdLoadRefresh, signOut, tokenStore } from '@/shared/utils/api-client';
import { defaultFormatContext, type FormatContext } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';
import { createPasskey, getPasskey } from '@/shared/webauthn';

// Query keys, invalidation and the ceremonies (playbook 6.1). Screens call
// these and render; nothing here knows a role name.

export const identityKeys = {
  me: ['me'] as const,
  passkeys: ['me', 'passkeys'] as const,
  sessions: ['me', 'sessions'] as const,
};

export type SessionStatus = 'loading' | 'anonymous' | 'enrolment' | 'signed-in' | 'error';

export interface SessionState {
  status: SessionStatus;
  me: Me | null;
  error: unknown;
  refetch: () => void;
}

// One refresh attempt on a cold load; a visitor without a cookie costs no
// GET /me. A 401 from /me (session ended elsewhere) is "anonymous", not an error.
async function fetchSession(): Promise<Me | null> {
  const { token, outcome, error: refreshError } = await ensureColdLoadRefresh();
  // A server that did not answer is a connection state, not a sign-out: the
  // gate offers "Try again" instead of sending the person to /sign-in and
  // losing what they were doing (chunk 1 review, security item 2).
  if (outcome === 'unavailable') throw refreshError instanceof Error ? refreshError : new Error('The session could not be refreshed.');
  if (token === null) return null;
  try {
    return await identity.getMe();
  } catch (error) {
    if (problemStatus(error) === 401) {
      tokenStore.clear();
      return null;
    }
    throw error;
  }
}

export function sessionStatusOf(query: Pick<UseQueryResult<Me | null>, 'isPending' | 'isError' | 'data'>): SessionStatus {
  if (query.isPending) return 'loading';
  if (query.isError) return 'error';
  if (query.data === null || query.data === undefined) return 'anonymous';
  return query.data.enrolmentPending ? 'enrolment' : 'signed-in';
}

export function useSession(): SessionState {
  const query = useQuery({ queryKey: identityKeys.me, queryFn: fetchSession, staleTime: 60_000, retry: false });
  return { status: sessionStatusOf(query), me: query.data ?? null, error: query.error, refetch: () => void query.refetch() };
}

export function userLocaleOf(me: Me | null): Locale {
  const locale = me?.user.locale;
  return isLocale(locale) ? locale : defaultLocale;
}

export function useFormatContext(): FormatContext {
  const { me } = useSession();
  return { locale: userLocaleOf(me), timeZone: me?.tenant?.timezone ?? defaultFormatContext.timeZone };
}

function useInvalidateSession(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: identityKeys.me });
}

export function useOpenInvitation(): UseMutationResult<void, unknown, string> {
  return useMutation({ mutationFn: (token: string) => identity.openInvitation(token) });
}

export function useRequestCode(): UseMutationResult<void, unknown, string> {
  return useMutation({ mutationFn: (email: string) => identity.requestCode({ email }) });
}

export function useVerifyCode(): UseMutationResult<TokenResponse, unknown, { email: string; code: string }> {
  const invalidate = useInvalidateSession();
  return useMutation({
    mutationFn: (body) => identity.verifyCode(body),
    onSuccess: async (response) => {
      tokenStore.set(response.accessToken);
      await invalidate();
    },
  });
}

// The invitation path: the token held in memory since the link was opened,
// and the code; no address.
export function useVerifyInvitationCode(): UseMutationResult<TokenResponse, unknown, { token: string; code: string }> {
  const invalidate = useInvalidateSession();
  return useMutation({
    mutationFn: (body) => identity.verifyInvitationCode(body),
    onSuccess: async (response) => {
      tokenStore.set(response.accessToken);
      await invalidate();
    },
  });
}

// Options, the browser ceremony, verify. From an enrolment session the first
// passkey returns the full session's access token. No name is sent: the server
// names the passkey from the device and returns it on `passkey.nickname`
// (ID-04); renaming stays under My passkeys.
export function useRegisterPasskey(): UseMutationResult<RegisterVerifyResponse, unknown, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const options = await identity.registerOptions();
      const credential = await createPasskey(options);
      return identity.registerVerify({ credential });
    },
    onSuccess: async (response) => {
      // An enrolment session is upgraded to a full one; a full session adds a passkey and keeps its token.
      if (typeof response.accessToken === 'string' && response.accessToken.length > 0) tokenStore.set(response.accessToken);
      await queryClient.invalidateQueries({ queryKey: identityKeys.me });
    },
  });
}

export function useSignIn(): UseMutationResult<TokenResponse, unknown, void> {
  const invalidate = useInvalidateSession();
  return useMutation({
    mutationFn: async () => {
      const options = await identity.authenticateOptions();
      const credential = await getPasskey(options);
      return identity.authenticateVerify({ credential });
    },
    onSuccess: async (response) => {
      tokenStore.set(response.accessToken);
      await invalidate();
    },
  });
}

export function useStepUp(): UseMutationResult<StepUpVerifyResponse, unknown, void> {
  const invalidate = useInvalidateSession();
  return useMutation({
    mutationFn: async () => {
      const options = await identity.stepUpOptions();
      const credential = await getPasskey(options);
      return identity.stepUpVerify({ credential });
    },
    onSuccess: () => invalidate(),
  });
}

export function useSignOut(): UseMutationResult<void, unknown, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => signOut(),
    onSettled: () => {
      queryClient.clear();
    },
  });
}

export function usePasskeys(enabled = true): UseQueryResult<Passkey[]> {
  return useQuery({ queryKey: identityKeys.passkeys, queryFn: identity.listPasskeys, enabled });
}

export function useRenamePasskey(): UseMutationResult<Passkey, unknown, { id: string; nickname: string }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, nickname }) => identity.renamePasskey(id, { nickname }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: identityKeys.passkeys }),
  });
}

export function useRemovePasskey(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => identity.removePasskey(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: identityKeys.passkeys });
      await queryClient.invalidateQueries({ queryKey: identityKeys.me });
    },
  });
}

export function useAddPasskey(): UseMutationResult<RegisterVerifyResponse, unknown, void> {
  const queryClient = useQueryClient();
  const register = useRegisterPasskey();
  return {
    ...register,
    mutateAsync: async () => {
      const response = await register.mutateAsync();
      await queryClient.invalidateQueries({ queryKey: identityKeys.passkeys });
      return response;
    },
  } as UseMutationResult<RegisterVerifyResponse, unknown, void>;
}

export function useSessions(enabled = true): UseQueryResult<UserSession[]> {
  return useQuery({ queryKey: identityKeys.sessions, queryFn: identity.listSessions, enabled });
}

export function useRevokeSession(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => identity.revokeSession(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: identityKeys.sessions }),
  });
}
