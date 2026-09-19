'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, useSyncExternalStore, type FormEvent } from 'react';

import { AuthPanel, StepKicker } from '@/components/auth/AuthFrame';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { InputOtp, OTP_LENGTH } from '@/components/ui/input-otp';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useOpenInvitation, useRegisterPasskey, useRequestCode, useSession, useVerifyCode, useVerifyInvitationCode } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { tokenStore } from '@/shared/utils/api-client';
import { hasProblemCode, problemStatus } from '@/shared/utils/problem';
import { WebAuthnFailure } from '@/shared/webauthn';

// Enrolment (design/screens/auth-code.html and auth-enrol.html; ID-02,
// ID-03): the code once, the first passkey, then the offer of a second one.
// A visitor starts at the code; an enrolment session starts at the passkey;
// a full session that did not just enrol here goes to Today.
// The passkey is not named here: the server names it from the device (the
// authenticator, else the browser and platform, else the transport) and the
// confirmation shows that name; renaming stays under My passkeys (ID-04,
// Alex 2026-09-19).

type Step = 'code' | 'passkey' | 'second';

/**
 * The address the invitation screen leaves in the bar (never the token). A
 * reload there has lost the token held in memory, so the code step asks for
 * the link again instead of falling back to an email field.
 */
export const INVITATION_ENROL_PATH = '/enrol?via=invitation';

function subscribeNever(): () => void {
  return () => undefined;
}

function cameFromInvitation(): boolean {
  return new URLSearchParams(window.location.search).get('via') === 'invitation';
}

function ReopenLink() {
  const t = useT();
  return (
    <AuthPanel aria-labelledby="code-title">
      <StepKicker>{t('auth.code.step')}</StepKicker>
      <h1 id="code-title" className="mb-2">
        {t('auth.code.title')}
      </h1>
      <p className="mb-5 text-muted">{t('auth.code.reopenLink')}</p>
      <ButtonBar>
        <Link href="/sign-in" className="inline-flex h-9 items-center rounded-control border border-line-control bg-surface px-4 font-medium no-underline hover:hover-fill">
          {t('auth.invitation.goToSignIn')}
        </Link>
      </ButtonBar>
    </AuthPanel>
  );
}

// Two doors to the same code step. With the invitation's token (held in
// React state since the link was opened, never in the URL or storage) only
// the code is asked for, and "Send a new code" opens the same invitation
// again. Without it (the sign-in page's "First time here?") the address is
// asked for too, and a new code is requested neutrally (AC-ID1).
function CodeStep({ invitationToken, onVerified }: { invitationToken: string | null; onVerified: () => void }) {
  const t = useT();
  const requestCode = useRequestCode();
  const reopen = useOpenInvitation();
  const verifyByEmail = useVerifyCode();
  const verifyByToken = useVerifyInvitationCode();
  const verify = invitationToken === null ? verifyByEmail : verifyByToken;
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [missing, setMissing] = useState(false);
  const [sentOnce, setSentOnce] = useState(false);

  const submitCode = (value: string) => {
    if (value.length !== OTP_LENGTH || (invitationToken === null && email.trim() === '')) {
      setMissing(true);
      return;
    }
    setMissing(false);
    if (invitationToken === null) verifyByEmail.mutate({ email: email.trim(), code: value }, { onSuccess: onVerified });
    else verifyByToken.mutate({ token: invitationToken, code: value }, { onSuccess: onVerified });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    submitCode(code);
  };

  const sendNew = () => {
    setSentOnce(false);
    if (invitationToken !== null) {
      reopen.mutate(invitationToken, { onSuccess: () => setSentOnce(true) });
      return;
    }
    if (email.trim() === '') {
      setMissing(true);
      return;
    }
    setMissing(false);
    requestCode.mutate(email.trim(), { onSettled: () => setSentOnce(true) });
  };

  const locked = hasProblemCode(verify.error, 'code_locked');
  const invalid = hasProblemCode(verify.error, 'invalid_code');
  const gone = problemStatus(verify.error) === 410 || problemStatus(reopen.error) === 410;

  return (
    <form onSubmit={submit} aria-labelledby="code-title" aria-busy={verify.isPending} noValidate>
      <AuthPanel>
        <StepKicker>{t('auth.code.step')}</StepKicker>
        <h1 id="code-title" className="mb-2">
          {t('auth.code.title')}
        </h1>
        <p className="mb-5 text-muted">{t('auth.code.lede')}</p>
        {invitationToken === null ? (
          <Field id="enrol-email" label={t('auth.code.email')}>
            <TextInput id="enrol-email" type="email" autoComplete="email" placeholder={t('auth.code.emailPlaceholder')} value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
        ) : null}
        <Field id="enrol-code" label={t('auth.code.code')} hint={t('auth.code.codeHint')}>
          <InputOtp id="enrol-code" value={code} onChange={setCode} onComplete={submitCode} invalid={invalid || locked} disabled={verify.isPending} describedBy="enrol-code-hint" />
        </Field>
        {missing ? (
          <p role="alert" className="text-meta text-negative">
            {invitationToken === null ? t('auth.code.required') : t('auth.code.codeRequired')}
          </p>
        ) : null}
        {gone ? (
          <p role="alert" className="text-meta text-negative">
            {t('auth.invitation.expired')}
          </p>
        ) : invalid ? (
          <p role="alert" className="text-meta text-negative">
            {t('auth.code.invalid')}
          </p>
        ) : locked ? (
          <p role="alert" className="text-meta text-negative">
            {t('auth.code.locked')}
          </p>
        ) : verify.isError ? (
          <ProblemAlert error={verify.error} />
        ) : reopen.isError ? (
          <ProblemAlert error={reopen.error} />
        ) : null}
        {/* The sign-in path says the same sentence whatever the server did: an enrolled address learns nothing (AC-ID1). */}
        {sentOnce ? <StatusLine>{invitationToken === null ? t('auth.code.neutral') : t('auth.code.resent')}</StatusLine> : null}
        <ButtonBar>
          <Button variant="outline" onClick={sendNew} disabled={requestCode.isPending || reopen.isPending || gone}>
            {t('auth.code.sendNew')}
          </Button>
          <Button type="submit" disabled={verify.isPending || locked || gone}>
            {t('auth.code.continue')}
          </Button>
        </ButtonBar>
      </AuthPanel>
    </form>
  );
}

function PasskeyStep({ second, onRegistered, onSessionEnded }: { second: boolean; onRegistered: (nickname: string) => void; onSessionEnded: () => void }) {
  const t = useT();
  const register = useRegisterPasskey();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    register.mutate(undefined, { onSuccess: (response) => onRegistered(response.passkey.nickname) });
  };

  const failure = register.error;
  const ended = !(failure instanceof WebAuthnFailure) && (problemStatus(failure) === 401 || problemStatus(failure) === 403);

  return (
    <form onSubmit={submit} aria-labelledby="passkey-title" aria-busy={register.isPending} noValidate>
      <AuthPanel>
        <StepKicker>{second ? t('auth.enrol.step3') : t('auth.enrol.step2')}</StepKicker>
        <h1 id="passkey-title" className="mb-2">
          {t('auth.enrol.title')}
        </h1>
        <p className="mb-5 text-muted">{t('auth.enrol.lede')}</p>
        {failure instanceof WebAuthnFailure ? (
          <p role="alert" className="text-meta text-negative">
            {failure.kind === 'already_registered' ? t('auth.enrol.alreadyRegistered') : t('auth.enrol.cancelled')}
          </p>
        ) : ended ? (
          <p role="alert" className="text-meta text-negative">
            {t('auth.enrol.expired')}
          </p>
        ) : register.isError ? (
          <ProblemAlert error={failure} />
        ) : null}
        {register.isPending ? <StatusLine>{t('auth.enrol.waitingHint')}</StatusLine> : null}
        <ButtonBar>
          {ended ? (
            <Button variant="outline" onClick={onSessionEnded}>
              {t('auth.enrol.backToCode')}
            </Button>
          ) : null}
          <Button type="submit" disabled={register.isPending}>
            {register.isPending ? t('auth.enrol.waiting') : t('auth.enrol.create')}
          </Button>
        </ButtonBar>
      </AuthPanel>
    </form>
  );
}

function SecondStep({ added, onSkip, onAdd }: { added: string; onSkip: () => void; onAdd: () => void }) {
  const t = useT();
  return (
    <AuthPanel aria-labelledby="second-title">
      <StepKicker>{t('auth.enrol.step3')}</StepKicker>
      <h1 id="second-title" className="mb-2">
        {t('auth.enrol.secondTitle')}
      </h1>
      <StatusLine tone="positive">{t('auth.enrol.added', { name: added })}</StatusLine>
      <p className="mt-2 mb-5 text-muted">{t('auth.enrol.secondLede')}</p>
      <ButtonBar>
        <Button variant="outline" onClick={onSkip}>
          {t('auth.enrol.skip')}
        </Button>
        <Button onClick={onAdd}>{t('auth.enrol.addAnother')}</Button>
      </ButtonBar>
    </AuthPanel>
  );
}

export function EnrolScreen({ invitationToken = null }: { invitationToken?: string | null }) {
  const t = useT();
  const router = useRouter();
  const session = useSession();
  const [chosen, setStep] = useState<Step | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  // The server renders "not from an invitation"; the browser answers after hydration.
  const reloadedInvitation = useSyncExternalStore(subscribeNever, cameFromInvitation, () => false) && invitationToken === null;

  // Until the person moves, the step follows the session: a visitor starts
  // at the code, an enrolment session at the passkey.
  const step: Step | null = chosen ?? (session.status === 'anonymous' ? 'code' : session.status === 'enrolment' ? 'passkey' : null);

  useEffect(() => {
    if (chosen === null && session.status === 'signed-in') router.replace('/');
  }, [chosen, session.status, router]);

  if (step === null) {
    return (
      <AuthPanel role="status" aria-busy="true">
        <StatusLine>{t('common.loading')}</StatusLine>
      </AuthPanel>
    );
  }
  if (step === 'code') {
    if (reloadedInvitation) return <ReopenLink />;
    return <CodeStep invitationToken={invitationToken} onVerified={() => setStep('passkey')} />;
  }
  if (step === 'passkey') {
    return (
      <PasskeyStep
        second={added !== null}
        onRegistered={(nickname) => {
          if (added !== null) {
            router.replace('/');
            return;
          }
          setAdded(nickname);
          setStep('second');
        }}
        onSessionEnded={() => {
          tokenStore.clear();
          setStep('code');
        }}
      />
    );
  }
  return <SecondStep added={added ?? ''} onSkip={() => router.replace('/')} onAdd={() => setStep('passkey')} />;
}
