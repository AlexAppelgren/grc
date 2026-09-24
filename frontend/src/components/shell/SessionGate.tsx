'use client';

import { useIsMutating } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { ErrorState } from '@/components/ui/States';
import { signOutKey, userLocaleOf, useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PUBLIC_HOME } from '@/shared/navigation/registry';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

// Every tenant screen sits behind this gate: a visitor with no session goes to
// the public page, whether they never signed in, signed out, or their session
// ended by itself (idle, revoked, past its limit; the next request finds out),
// and signs in from there. An enrolment session goes to /enrol (it can reach
// nothing else, AC-ID2), and a signed-in person gets the permission list for
// the client gate and the catalog in their own language. While a sign-out is pending
// the screens are taken down first, so none of them asks the server for
// anything once the session has ended.

export function SessionGate({ children }: { children: ReactNode }) {
  const t = useT();
  const router = useRouter();
  const session = useSession();
  const signingOut = useIsMutating({ mutationKey: signOutKey }) > 0;

  useEffect(() => {
    if (session.status === 'anonymous') router.replace(PUBLIC_HOME);
    if (session.status === 'enrolment') router.replace('/enrol');
  }, [session.status, router]);

  if (session.status === 'error') {
    return (
      <div className="mx-auto max-w-[60ch] px-4 py-16">
        <ErrorState title={t('common.errorTitle')} onRetry={session.refetch} />
      </div>
    );
  }
  if (signingOut || session.status !== 'signed-in' || session.me === null) {
    return (
      <div role="status" aria-busy="true" className="grid min-h-screen place-items-center text-muted" data-session-loading="">
        {t('shell.loading')}
      </div>
    );
  }
  return (
    <LocaleProvider locale={userLocaleOf(session.me)}>
      <PermissionsProvider permissions={session.me.permissions}>{children}</PermissionsProvider>
    </LocaleProvider>
  );
}
