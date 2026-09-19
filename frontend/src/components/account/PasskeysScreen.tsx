'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useAddPasskey, useFormatContext, usePasskeys, useRemovePasskey, useRenamePasskey } from '@/features/identity/hooks';
import { presentPasskey } from '@/features/identity/identity-presentation';
import type { Passkey } from '@/features/identity/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatDateTime } from '@/shared/utils/format';
import { WebAuthnFailure } from '@/shared/webauthn';

// My passkeys (design/screens/me-passkeys.html, ID-04): add, rename,
// remove, never the last one (the server's 409 last_passkey renders in place).
// Adding runs the same ceremony as enrolment and asks for no name: the server
// names the passkey from the device, the page says what it was called, and
// Rename is where a person changes it.

function PasskeyRow({ passkey, onlyOne }: { passkey: Passkey; onlyOne: boolean }) {
  const t = useT();
  const ctx = useFormatContext();
  const rename = useRenamePasskey();
  const remove = useRemovePasskey();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [nickname, setNickname] = useState(passkey.nickname);

  const saveName = (event: FormEvent) => {
    event.preventDefault();
    rename.mutate({ id: passkey.id, nickname: nickname.trim() }, { onSuccess: () => setEditing(false) });
  };

  return (
    <Row data-passkey-id={passkey.id}>
      {editing ? (
        <form onSubmit={saveName} noValidate>
          <Field id={`rename-${passkey.id}`} label={t('me.passkeys.name')}>
            <TextInput id={`rename-${passkey.id}`} value={nickname} onChange={(e) => setNickname(e.target.value)} />
          </Field>
          {rename.isError ? <ProblemAlert error={rename.error} /> : null}
          <ButtonBar className="mt-0">
            <Button variant="outline" size="small" onClick={() => setEditing(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" size="small" disabled={rename.isPending}>
              {t('common.save')}
            </Button>
          </ButtonBar>
        </form>
      ) : (
        <div className="grid gap-2 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <h3 className="mb-1 font-semibold">{passkey.nickname}</h3>
            <Meta>
              <PillRow pills={presentPasskey(passkey, t)} />
              <span>{t('me.passkeys.added', { date: formatDate(passkey.createdAt, ctx) })}</span>
              <span>{passkey.lastUsedAt === null ? t('me.passkeys.neverUsed') : t('me.passkeys.lastUsed', { date: formatDateTime(passkey.lastUsedAt, ctx) })}</span>
            </Meta>
            {remove.isError ? <ProblemAlert error={remove.error} codes={{ last_passkey: t('me.passkeys.lastPasskey') }} /> : null}
            {confirming ? <StatusLine>{t('me.passkeys.removeConfirm')}</StatusLine> : null}
          </div>
          <ButtonBar className="mt-0">
            {confirming ? (
              <>
                <Button variant="outline" size="small" onClick={() => setConfirming(false)}>
                  {t('common.cancel')}
                </Button>
                <Button variant="danger" size="small" disabled={remove.isPending} onClick={() => remove.mutate(passkey.id, { onSettled: () => setConfirming(false) })}>
                  {t('me.passkeys.remove')}
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" size="small" onClick={() => setEditing(true)}>
                  {t('me.passkeys.rename')}
                </Button>
                {/* Stays pressable with one passkey: the server's 409 last_passkey is the answer (ID-S10). */}
                <Button variant="danger" size="small" onClick={() => setConfirming(true)} data-only-one={onlyOne ? '' : undefined}>
                  {t('me.passkeys.remove')}
                </Button>
              </>
            )}
          </ButtonBar>
        </div>
      )}
    </Row>
  );
}

function AddPasskeyModal({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: (nickname: string) => void }) {
  const t = useT();
  const add = useAddPasskey();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate(undefined, {
      onSuccess: (response) => {
        onAdded(response.passkey.nickname);
        onClose();
      },
    });
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={t('me.passkeys.addTitle')}>
      <form onSubmit={submit} noValidate aria-busy={add.isPending}>
        <p className="mb-5 text-muted">{t('me.passkeys.addLede')}</p>
        {add.error instanceof WebAuthnFailure ? (
          <p role="alert" className="text-meta text-negative">
            {add.error.kind === 'already_registered' ? t('auth.enrol.alreadyRegistered') : t('auth.enrol.cancelled')}
          </p>
        ) : add.isError ? (
          <ProblemAlert error={add.error} />
        ) : null}
        {add.isPending ? <StatusLine>{t('auth.enrol.waitingHint')}</StatusLine> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={add.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={add.isPending}>
            {add.isPending ? t('auth.enrol.waiting') : t('auth.enrol.create')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function PasskeysScreen() {
  const t = useT();
  const passkeys = usePasskeys();
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState<string | null>(null);

  return (
    <>
      <PageHead title={t('me.passkeys.title')} lede={t('me.passkeys.lede')} actions={<Button onClick={() => setAdding(true)}>{t('me.passkeys.add')}</Button>} />
      {added !== null ? (
        <StatusLine tone="positive">{t('auth.enrol.added', { name: added })}</StatusLine>
      ) : null}
      {passkeys.isPending ? (
        <LoadingState />
      ) : passkeys.isError ? (
        <ErrorState title={t('me.passkeys.errorTitle')} onRetry={() => void passkeys.refetch()} />
      ) : passkeys.data.length === 0 ? (
        <EmptyState title={t('me.passkeys.emptyTitle')} body={t('me.passkeys.emptyBody')} />
      ) : (
        <Rows>
          {passkeys.data.map((passkey) => (
            <PasskeyRow key={passkey.id} passkey={passkey} onlyOne={passkeys.data.length === 1} />
          ))}
        </Rows>
      )}
      <AddPasskeyModal open={adding} onClose={() => setAdding(false)} onAdded={setAdded} />
    </>
  );
}
