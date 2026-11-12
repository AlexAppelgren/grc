'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef } from 'react';

import { AuthPanel } from '@/components/auth/AuthFrame';
import { Button, ButtonBar } from '@/components/ui/Button';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useAddPasskey, useClaimDeviceLink, useDeviceLinkApproved, useSession, useStartDeviceLink } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { homeOf } from '@/shared/navigation/registry';
import { problemStatus } from '@/shared/utils/problem';
import { WebAuthnFailure } from '@/shared/webauthn';

// Add this device (D-135, ID-04): for a device that cannot reach the person's
// passkey, such as a laptop without Bluetooth when the passkey is on a phone.
// It shows a code; the person approves it on My passkeys on a device where they
// are signed in; this page notices, collects the session and offers to create a
// passkey here. The secret stays in this component's memory and never in the
// address, storage or a log.

/** `K7MPQ2XD` as `K7MP-Q2XD`, easier to read off one screen and type on another. */
export function formatDeviceCode(code: string): string {
  return code.length === 8 ? `${code.slice(0, 4)}-${code.slice(4)}` : code;
}

export function AddDeviceScreen() {
  const t = useT();
  const router = useRouter();
  const session = useSession();
  const start = useStartDeviceLink();
  const claim = useClaimDeviceLink();
  const add = useAddPasskey();
  const secret = start.data?.secret ?? null;
  const approved = useDeviceLinkApproved(claim.isIdle ? secret : null);
  const started = useRef(false);
  const { mutate: startLink } = start;
  const { mutate: claimLink } = claim;

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    startLink();
  }, [startLink]);

  useEffect(() => {
    if (approved.data === true && secret !== null && claim.isIdle) claimLink(secret);
  }, [approved.data, secret, claim.isIdle, claimLink]);

  const goHome = () => router.replace(homeOf(session.me));

  if (claim.isSuccess) {
    return (
      <AuthPanel aria-labelledby="add-device-title" aria-busy={add.isPending}>
        <h1 id="add-device-title" className="mb-2">
          {t('auth.addDevice.signedInTitle')}
        </h1>
        <p className="mb-5 text-muted">{t('auth.addDevice.signedInLede')}</p>
        {add.isSuccess ? <StatusLine tone="positive">{t('auth.enrol.added', { name: add.data.passkey.nickname })}</StatusLine> : null}
        {add.error instanceof WebAuthnFailure ? (
          <p role="alert" className="text-meta text-negative">
            {add.error.kind === 'already_registered' ? t('auth.enrol.alreadyRegistered') : t('auth.enrol.cancelled')}
          </p>
        ) : add.isError ? (
          <ProblemAlert error={add.error} />
        ) : null}
        {add.isPending ? <StatusLine>{t('auth.enrol.waitingHint')}</StatusLine> : null}
        <ButtonBar>
          {add.isSuccess ? (
            <Button onClick={goHome}>{t('auth.code.continue')}</Button>
          ) : (
            <>
              <Button variant="outline" onClick={goHome}>
                {t('auth.addDevice.later')}
              </Button>
              <Button disabled={add.isPending} onClick={() => add.mutate()}>
                {add.isPending ? t('auth.enrol.waiting') : t('auth.enrol.create')}
              </Button>
            </>
          )}
        </ButtonBar>
      </AuthPanel>
    );
  }

  const failure = start.error ?? approved.error ?? claim.error;
  const expired = problemStatus(approved.error) === 410 || problemStatus(claim.error) === 410;
  const again = () => {
    claim.reset();
    start.mutate();
  };
  return (
    <AuthPanel aria-labelledby="add-device-title" aria-busy={start.isPending}>
      <h1 id="add-device-title" className="mb-2">
        {t('auth.addDevice.title')}
      </h1>
      <p className="mb-5 text-muted">{t('auth.addDevice.lede')}</p>
      {expired ? (
        <p role="alert" className="text-meta text-negative">
          {t('auth.addDevice.expired')}
        </p>
      ) : failure !== null && failure !== undefined ? (
        <ProblemAlert error={failure} />
      ) : start.data !== undefined ? (
        <>
          <p className="microlabel mb-1">{t('auth.addDevice.codeLabel')}</p>
          <p className="mb-2 font-mono text-display" data-testid="device-code">
            {formatDeviceCode(start.data.code)}
          </p>
          <p className="text-meta text-muted">{t('auth.addDevice.hint')}</p>
          <StatusLine>{t('auth.addDevice.waiting')}</StatusLine>
        </>
      ) : (
        <StatusLine>{t('auth.addDevice.starting')}</StatusLine>
      )}
      {expired || (failure !== null && failure !== undefined) ? (
        <ButtonBar>
          <Button onClick={again} disabled={start.isPending}>
            {t('auth.addDevice.startAgain')}
          </Button>
        </ButtonBar>
      ) : null}
    </AuthPanel>
  );
}
