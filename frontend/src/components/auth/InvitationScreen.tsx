'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { AuthPanel } from '@/components/auth/AuthFrame';
import { EnrolScreen, INVITATION_ENROL_PATH } from '@/components/auth/EnrolScreen';
import { Button, ButtonBar } from '@/components/ui/Button';
import { StatusLine } from '@/components/ui/States';
import { useOpenInvitation } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { problemStatus } from '@/shared/utils/problem';

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
// renders: never in the URL, localStorage, sessionStorage or a log (F28).

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

export function InvitationScreen() {
  const t = useT();
  const open = useOpenInvitation();
  const started = useRef(false);
  // undefined until the address has been read (after hydration), null when it held no token.
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const { mutate } = open;

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    // Read and cleared before any request, so the back button, a shared
    // screen and every request this page makes carry nothing. Held in memory,
    // so Try again and Send a new code still work.
    const found = takeTokenFromHash();
    setToken(found);
    if (found !== null) mutate(found);
  }, [mutate]);

  // No token in the link: the code step asks for the link again.
  if (token === null) return <EnrolScreen />;
  if (token !== undefined && open.isSuccess) return <EnrolScreen invitationToken={token} />;

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
            <Link href="/sign-in" className="inline-flex min-h-11 items-center rounded-full border border-line-strong px-5 py-2.5 font-semibold no-underline">
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
