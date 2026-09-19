'use client';

import Link from 'next/link';
import { useEffect, useRef } from 'react';

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
// The token lives only in this component's props and the enrolment flow it
// renders: never in the URL once opened, never in localStorage,
// sessionStorage or a log (chunk 1 review, F28).

/**
 * Drops the token from the address without a navigation, so the browser keeps
 * no history entry holding it. A runtime without `history` (a test renderer,
 * a server pass) is left alone.
 */
export function replaceWithEnrol(): void {
  if (typeof window === 'undefined' || typeof window.history?.replaceState !== 'function') return;
  window.history.replaceState(null, '', INVITATION_ENROL_PATH);
}

export function InvitationScreen({ token }: { token: string }) {
  const t = useT();
  const open = useOpenInvitation();
  const started = useRef(false);
  const { mutate } = open;

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    // The token must not linger in history or leak through Referer. The
    // address becomes /enrol before the code is asked for, so the back
    // button, a shared screen and every request this page makes carry
    // nothing. The token itself is held in memory, so Try again and Send a
    // new code still work.
    replaceWithEnrol();
    mutate(token);
  }, [mutate, token]);

  if (open.isSuccess) return <EnrolScreen invitationToken={token} />;

  const gone = open.isError && problemStatus(open.error) === 410;

  return (
    <AuthPanel aria-labelledby="invitation-title" aria-busy={open.isPending}>
      <h1 id="invitation-title" className="mb-2">
        {t('auth.invitation.title')}
      </h1>
      {open.isError ? (
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
