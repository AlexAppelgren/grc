'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { ErrorState } from '@/components/ui/States';
import { userLocaleOf, useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PUBLIC_HOME } from '@/shared/navigation/registry';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

// Every tenant screen sits behind this gate: an anonymous visitor goes to
// /sign-in, or to the public page when they came to / (the site's front door,
// not a deep link), an enrolment session to /enrol (it can reach nothing else,
// AC-ID2), and a signed-in person gets the permission list for the client
// gate and the catalog in their own language.

export function SessionGate({ children }: { children: ReactNode }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const session = useSession();

  useEffect(() => {
    if (session.status === 'anonymous') router.replace(pathname === '/' ? PUBLIC_HOME : '/sign-in');
    if (session.status === 'enrolment') router.replace('/enrol');
  }, [session.status, router, pathname]);

  if (session.status === 'error') {
    return (
      <div className="mx-auto max-w-[60ch] px-4 py-16">
        <ErrorState title={t('common.errorTitle')} onRetry={session.refetch} />
      </div>
    );
  }
  if (session.status !== 'signed-in' || session.me === null) {
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
