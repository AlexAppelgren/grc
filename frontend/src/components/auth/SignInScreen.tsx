'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState, useSyncExternalStore } from 'react';

import { AuthPanel } from '@/components/auth/AuthFrame';
import { Button, ButtonBar } from '@/components/ui/Button';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useSession, useSignIn } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { problemStatus } from '@/shared/utils/problem';
import { isWebAuthnAvailable, WebAuthnFailure } from '@/shared/webauthn';

// Sign in (design/screens/auth-sign-in.html, ID-03): one action, no
// username, the passkey is discoverable. The recovery panel
// (auth-recovery.html) is a state of this screen, not a route.

function subscribeNever(): () => void {
  return () => undefined;
}

function RecoveryPanel({ onBack }: { onBack: () => void }) {
  const t = useT();
  return (
    <AuthPanel aria-labelledby="recovery-title">
      <h1 id="recovery-title" className="mb-2">
        {t('auth.recovery.title')}
      </h1>
      <p className="text-muted">{t('auth.recovery.lede')}</p>
      <div className="my-3.5 rounded-s bg-sand px-3.5 py-3">{t('auth.recovery.body')}</div>
      <p className="text-muted">{t('auth.recovery.lastAdmin')}</p>
      <ButtonBar>
        <Button variant="ghost" onClick={onBack}>
          {t('auth.recovery.back')}
        </Button>
      </ButtonBar>
    </AuthPanel>
  );
}

export function SignInScreen() {
  const t = useT();
  const router = useRouter();
  const session = useSession();
  const signIn = useSignIn();
  const [recovery, setRecovery] = useState(false);
  // The server renders "supported"; the browser answers for itself after hydration.
  const supported = useSyncExternalStore(subscribeNever, isWebAuthnAvailable, () => true);

  useEffect(() => {
    if (session.status === 'signed-in') router.replace('/');
    if (session.status === 'enrolment') router.replace('/enrol');
  }, [session.status, router]);

  if (recovery) return <RecoveryPanel onBack={() => setRecovery(false)} />;

  const failure = signIn.error;
  let failureText: string | null = null;
  if (failure instanceof WebAuthnFailure) {
    failureText = failure.kind === 'unsupported' ? t('auth.signIn.unsupported') : t('auth.signIn.cancelled');
  } else if (problemStatus(failure) === 401) {
    failureText = t('auth.signIn.refused');
  }

  return (
    <AuthPanel aria-labelledby="sign-in-title" aria-busy={signIn.isPending}>
      <h1 id="sign-in-title" className="mb-2">
        {t('auth.signIn.title')}
      </h1>
      <p className="mb-5 text-muted">{t('auth.signIn.lede')}</p>
      {supported ? (
        <Button className="w-full" disabled={signIn.isPending} onClick={() => signIn.mutate(undefined, { onSuccess: () => router.replace('/') })}>
          {signIn.isPending ? t('auth.signIn.waiting') : t('auth.signIn.button')}
        </Button>
      ) : (
        <p role="alert" className="text-meta text-negative">
          {t('auth.signIn.unsupported')}
        </p>
      )}
      {signIn.isPending ? <StatusLine>{t('auth.signIn.waitingHint')}</StatusLine> : null}
      {failureText !== null ? (
        <p role="alert" className="mt-2.5 text-meta text-negative">
          {failureText}
        </p>
      ) : failure !== null && failure !== undefined ? (
        <ProblemAlert error={failure} />
      ) : null}
      <div className="mt-5 grid gap-2 border-t border-line pt-4 text-meta">
        <button type="button" className="text-left font-semibold underline" onClick={() => router.push('/enrol')}>
          {t('auth.signIn.firstTime')}
        </button>
        <button type="button" className="text-left font-semibold underline" onClick={() => setRecovery(true)}>
          {t('auth.signIn.lostPasskeys')}
        </button>
      </div>
    </AuthPanel>
  );
}
