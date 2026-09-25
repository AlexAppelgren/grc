'use client';

import Link from 'next/link';
import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckRow } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert, StatusLine } from '@/components/ui/States';
import { AccessLog } from '@/features/agent-access/AccessLog';
import { EntryScope, SECURITY_HREF, useOrgReach } from '@/features/agent-access/AccessScreen';
import { Credentials } from '@/features/agent-access/Credentials';
import { EntryDialog } from '@/features/agent-access/EntryDialog';
import { useAccessEntry, useRevokeEntry, useSetEntryReach } from '@/features/agent-access/hooks';
import { presentEntry, refusals } from '@/features/agent-access/presentation';
import type { AccessEntry } from '@/features/agent-access/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// One entry (design/screens/admin-agent-access.html, states 6 to 15;
// ACC-01, ACC-02, ACC-03, ACC-08, J-11): what it reads, its own half of
// tenant reach, its credentials and its access log. Another organisation's
// entry, or none, is Not found. A revoked entry is read-only, its log kept.

const ACCESS_HREF = '/admin/agents/access';

function ReachPanel({ entry, orgReach }: { entry: AccessEntry; orgReach: boolean | null }) {
  const t = useT();
  const setReach = useSetEntryReach();
  // The entry's half is disabled while the organisation's half is off: a
  // change here could not reach anything, and the reason says where it is set.
  const disabled = !entry.active || orgReach === false || setReach.isPending;
  return (
    <Panel title={t('agentAccess.reach.title')} data-entry-reach="">
      <CheckRow id="entry-reach" label={t('agentAccess.reach.toggle')} hint={t('agentAccess.reach.toggleHint')} checked={entry.tenantReach} disabled={disabled} onChange={(enabled) => setReach.mutate({ entry, enabled })} />
      {orgReach === false ? (
        <p className="mt-2 text-meta text-muted" data-reach-off-reason="">
          {t('agentAccess.reach.offReason')}{' '}
          <Link href={SECURITY_HREF} className="font-semibold underline">
            {t('agentAccess.reachLine.go')}
          </Link>
        </p>
      ) : entry.active ? (
        <p className="mt-2 text-meta text-muted">{t('agentAccess.reach.changeHint')}</p>
      ) : null}
      {setReach.isError ? <ProblemAlert error={setReach.error} codes={refusals(t)} /> : null}
    </Panel>
  );
}

function RevokeDialog({ entry, onClose, onRevoked }: { entry: AccessEntry; onClose: () => void; onRevoked: () => void }) {
  const t = useT();
  const revoke = useRevokeEntry();
  return (
    <Modal open onOpenChange={(next) => (next ? undefined : onClose())} title={t('agentAccess.revoke.title', { name: entry.name })} description={t('agentAccess.revoke.body')}>
      {revoke.isError ? <ProblemAlert error={revoke.error} codes={refusals(t)} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={onClose} disabled={revoke.isPending}>
          {t('agentAccess.revoke.keep')}
        </Button>
        <Button variant="danger" disabled={revoke.isPending} onClick={() => revoke.mutate(entry, { onSuccess: onRevoked })}>
          {t('agentAccess.revoke.confirm')}
        </Button>
      </ButtonBar>
      <p className="mt-2 text-meta text-muted">{t('agentAccess.revoke.stepUpHint')}</p>
    </Modal>
  );
}

function Entry({ entry, onReload }: { entry: AccessEntry; onReload: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const orgReach = useOrgReach();
  const [dialog, setDialog] = useState<'edit' | 'revoke' | null>(null);
  const [revoked, setRevoked] = useState(false);

  const actions = entry.active ? (
    <ButtonBar className="mt-0">
      <Button variant="danger" onClick={() => setDialog('revoke')}>
        {t('agentAccess.entry.revoke')}
      </Button>
      <Button onClick={() => setDialog('edit')}>{t('agentAccess.entry.edit')}</Button>
    </ButtonBar>
  ) : null;

  return (
    <div data-entry={entry.id}>
      <BackLink href={ACCESS_HREF} label={t('agentAccess.back')} />
      <PageHead title={entry.name} actions={actions} />
      <div className="mb-2">
        <PillRow pills={presentEntry(entry, orgReach, t)} />
      </div>
      <p className="mb-4 text-muted">{entry.purpose}</p>
      {revoked ? <StatusLine tone="positive">{t('agentAccess.revoke.done')}</StatusLine> : null}
      {!entry.active ? (
        <p className="mb-4 text-muted" data-entry-revoked="">
          {entry.revokedBy ? t('agentAccess.revokedBy', { date: formatDate(entry.revokedAt ?? entry.createdAt, ctx), name: entry.revokedBy.name }) : t('agentAccess.revokedOn', { date: formatDate(entry.revokedAt ?? entry.createdAt, ctx) })}{' '}
          {t('agentAccess.entry.revokedNote')}
        </p>
      ) : null}
      <Panel title={t('agentAccess.entry.whatItReads')}>
        <div className="grid gap-1.5">
          <Meta>
            <span>{t('agentAccess.ownedBy', { team: entry.ownerTeam.label })}</span>
          </Meta>
          <EntryScope entry={entry} />
          <Meta>
            <span>{t('agentAccess.entry.registeredBy', { date: formatDate(entry.createdAt, ctx), name: entry.createdBy.name })}</span>
          </Meta>
        </div>
        <p className="mt-3 text-meta text-muted">{t('agentAccess.entry.scopeNote')}</p>
      </Panel>
      <ReachPanel entry={entry} orgReach={orgReach} />
      <Credentials entry={entry} />
      <AccessLog entryId={entry.id} />
      {dialog === 'edit' ? (
        <EntryDialog key={entry.version} open entry={entry} onClose={() => setDialog(null)} onSaved={() => setDialog(null)} onReload={onReload} />
      ) : null}
      {dialog === 'revoke' ? (
        <RevokeDialog
          entry={entry}
          onClose={() => setDialog(null)}
          onRevoked={() => {
            setDialog(null);
            setRevoked(true);
          }}
        />
      ) : null}
    </div>
  );
}

export function EntryScreen({ entryId }: { entryId: string }) {
  const t = useT();
  const entry = useAccessEntry(entryId);
  if (entry.isPending) return <LoadingState />;
  if (entry.isError) {
    return problemStatus(entry.error) === 404 ? (
      <NotFoundScreen body={t('agentAccess.entry.notFound')} backHref={ACCESS_HREF} backLabel={t('agentAccess.back')} />
    ) : (
      <ErrorState title={t('agentAccess.entry.errorTitle')} onRetry={() => void entry.refetch()} />
    );
  }
  return <Entry entry={entry.data} onReload={() => void entry.refetch()} />;
}
