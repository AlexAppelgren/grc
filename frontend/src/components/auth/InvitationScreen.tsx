'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { AuthPanel } from '@/components/auth/AuthFrame';
import { EnrolScreen, INVITATION_ENROL_PATH } from '@/components/auth/EnrolScreen';
import { Button, ButtonBar } from '@/components/ui/Button';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { dropHeldInvitation, heldInvitation } from '@/features/identity/held-invitation';
import { useAcceptInvitation, useOpenInvitation, useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { homeOf } from '@/shared/navigation/registry';
import { hasProblemCode, problemStatus } from '@/shared/utils/problem';

// The invitation landing (design/screens/auth-invitation.html, ID-01,
// ID-02): opening the link asks the server to send the code, then the code
// step follows in place. The token names the account, so no address is asked
// for: it is verified with the code (POST /auth/invitations/verify). The page
// never shows the address or the code; 410 means expired or already used.
//
// The emailed link is /invite#<token>: a fragment never reaches any server,
// proxy or Referer, so no request line holds the token (security review F29).
// It is read once, the address is replaced before any request, and from then
// on it lives only in this component's state and the enrolment flow it
// renders: never in the URL, localStorage or a log (F28). One exception:
// a person who already holds a passkey (D-122) is never sent a code, so the
// code step offers "Sign in and join", and the token waits in this tab's
// sessionStorage across the sign-in (`holdInvitation`) until the join
// succeeds or the invitation answers 410. A signed-in visitor gets the join
// panel instead of a code; a visitor who is not signed in sees the same page
// whether or not the address holds a passkey.

/**
 * Drops the token from the address without a navigation, so the browser keeps
 * no history entry holding it. A runtime without `history` (a test renderer,
 * a server pass) is left alone.
 */
export function replaceWithEnrol(): void {
  if (typeof window === 'undefined' || typeof window.history?.replaceState !== 'function') return;
  window.history.replaceState(null, '', INVITATION_ENROL_PATH);
}

/** The token in the address's fragment, or null; the address is cleared either way. */
export function takeTokenFromHash(): string | null {
  const token = window.location.hash.slice(1);
  replaceWithEnrol();
  return token === '' ? null : token;
}

// D-122: a signed-in person joins with a passkey confirmation, then the browser
// loads the bank's home from the refresh cookie the switch set. A 410 is the
// same for an unknown, closed or someone else's invitation.
function JoinPanel({ token }: { token: string }) {
  const t = useT();
  const join = useAcceptInvitation((tenantId) => {
    dropHeldInvitation();
    window.location.assign(homeOf({ tenant: { id: tenantId } }));
  });
  const gone = problemStatus(join.error) === 410;
  useEffect(() => {
    if (gone) dropHeldInvitation();
  }, [gone]);

  return (
    <AuthPanel aria-labelledby="invitation-title" aria-busy={join.isPending}>
      <h1 id="invitation-title" className="mb-2">
        {t('auth.invitation.title')}
      </h1>
      <p className="mb-5 text-muted">{t('auth.invitation.joinLede')}</p>
      {gone ? (
        <p role="alert" className="text-meta text-negative">
          {t('auth.invitation.notOpen')}
        </p>
      ) : join.isError && !hasProblemCode(join.error, 'step_up_required') ? (
        <ProblemAlert error={join.error} />
      ) : null}
      <ButtonBar>
        <Button onClick={() => join.mutate(token)} disabled={join.isPending || gone}>
          {t('auth.invitation.join')}
        </Button>
      </ButtonBar>
    </AuthPanel>
  );
}

export function InvitationScreen() {
  const t = useT();
  const session = useSession();
  const open = useOpenInvitation();
  const started = useRef(false);
  const opened = useRef(false);
  // undefined until the address has been read (after hydration), null when it held no token.
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const { mutate } = open;
  const signedIn = session.status === 'signed-in';
  const settled = session.status !== 'loading';

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    // Read and cleared before any request, so the back button, a shared
    // screen and every request this page makes carry nothing. Held in memory,
    // so Try again and Send a new code still work. Back from a passkey sign-in
    // the token is the one this tab held.
    setToken(takeTokenFromHash() ?? heldInvitation());
  }, []);

  useEffect(() => {
    // A signed-in person joins with their passkey and is sent no code.
    if (opened.current || !settled || signedIn || typeof token !== 'string') return;
    opened.current = true;
    mutate(token);
  }, [mutate, settled, signedIn, token]);

  // No token in the link: the code step asks for the link again.
  if (token === null) return <EnrolScreen />;
  if (token !== undefined && open.isSuccess) return <EnrolScreen invitationToken={token} />;
  // Signed in before anything was opened: the enrolment that ends in a full
  // session here keeps its own steps instead.
  if (token !== undefined && signedIn && open.isIdle) return <JoinPanel token={token} />;

  const gone = open.isError && problemStatus(open.error) === 410;

  return (
    <AuthPanel aria-labelledby="invitation-title" aria-busy={open.isPending}>
      <h1 id="invitation-title" className="mb-2">
        {t('auth.invitation.title')}
      </h1>
      {open.isError && token !== undefined ? (
        <>
          <p role="alert" className="text-meta text-negative">
            {gone ? t('auth.invitation.expired') : t('auth.invitation.error')}
          </p>
          <ButtonBar>
            <Link href="/sign-in" className="inline-flex h-9 items-center rounded-control border border-line-control bg-surface px-4 font-medium no-underline hover:hover-fill">
              {t('auth.invitation.goToSignIn')}
            </Link>
            {gone ? null : <Button onClick={() => mutate(token)}>{t('common.tryAgain')}</Button>}
          </ButtonBar>
        </>
      ) : (
        <StatusLine>{t('auth.invitation.opening')}</StatusLine>
      )}
    </AuthPanel>
  );
}
