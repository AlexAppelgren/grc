'use client';

import Link from 'next/link';
import { useState } from 'react';

import { AgentsTabs } from '@/components/admin/AgentsScreen';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, StatusLine } from '@/components/ui/States';
import { EntryDialog } from '@/features/agent-access/EntryDialog';
import { useAccessEntries, useTenantReach } from '@/features/agent-access/hooks';
import { credentialCounts, presentEntry, presentUnits } from '@/features/agent-access/presentation';
import type { AccessEntry } from '@/features/agent-access/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// The Access tab of Agents (design/screens/admin-agent-access.html; ACC-01,
// ACC-02, ACC-08, J-11), for agent_access.manage alone (the registry's gate).
// The agents a bank runs on its own systems, which only read. The
// organisation's half of tenant reach lives on Security and is only named
// here, with a link: it is read under security.manage, and without that grant
// the line says where it is set rather than guessing its state.

const SECURITY_MANAGE = 'security.manage';

export const SECURITY_HREF = '/admin/security';

/** Whether the organisation's switch is on, or null when this person cannot read it. */
export function useOrgReach(): boolean | null {
  const canRead = (usePermissions() ?? []).includes(SECURITY_MANAGE);
  const reach = useTenantReach(canRead);
  return canRead && reach.isSuccess ? reach.data.enabled : null;
}

function ReachLine({ orgReach }: { orgReach: boolean | null }) {
  const t = useT();
  const text = orgReach === null ? t('agentAccess.reachLine.unknown') : orgReach ? t('agentAccess.reachLine.on') : t('agentAccess.reachLine.off');
  return (
    <Notice data-reach-line={orgReach === null ? 'unknown' : orgReach ? 'on' : 'off'}>
      {text}{' '}
      <Link href={SECURITY_HREF} className="font-semibold underline">
        {orgReach === true ? t('agentAccess.reachLine.change') : t('agentAccess.reachLine.go')}
      </Link>
    </Notice>
  );
}

/** Departments and products, or the plain words for no narrowing. */
export function EntryScope({ entry }: { entry: AccessEntry }) {
  const t = useT();
  if (entry.departments.length === 0 && entry.products.length === 0) {
    return (
      <Meta>
        <span>{t('agentAccess.reads')}</span>
        <span>{t('agentAccess.wholeScope')}</span>
      </Meta>
    );
  }
  return (
    <div className="grid gap-1.5">
      <Meta>
        <span>{t('agentAccess.departments')}</span>
        {entry.departments.length === 0 ? <span>{t('agentAccess.noneNamed')}</span> : <PillRow pills={presentUnits(entry.departments, 'department')} />}
      </Meta>
      <Meta>
        <span>{t('agentAccess.products')}</span>
        {entry.products.length === 0 ? <span>{t('agentAccess.noneNamed')}</span> : <PillRow pills={presentUnits(entry.products, 'product')} />}
      </Meta>
    </div>
  );
}

function EntryRow({ entry, orgReach }: { entry: AccessEntry; orgReach: boolean | null }) {
  const t = useT();
  const ctx = useFormatContext();
  const counts = credentialCounts(entry.keys);
  const credentials = [t('agentAccess.credentialCount', { keys: counts.keys }), ...(counts.tokens > 0 ? [t('agentAccess.tokenCount', { tokens: counts.tokens })] : [])].join(', ');
  const used = counts.lastUsedAt === null ? t('agentAccess.neverUsed') : t('agentAccess.lastUsed', { date: formatDateTime(counts.lastUsedAt, ctx) });
  const summary = [credentials, used].join(' · ');
  return (
    <Row data-entry-id={entry.id} data-entry-active={entry.active}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2 className="text-body font-semibold">
          <Link href={`/admin/agents/access/${encodeURIComponent(entry.id)}`} className="underline">
            {entry.name}
          </Link>
        </h2>
        <PillRow pills={presentEntry(entry, orgReach, t)} />
      </div>
      <p className="mb-2 text-muted">{entry.purpose}</p>
      <div className="grid gap-1.5">
        <Meta>
          <span>{t('agentAccess.ownedBy', { team: entry.ownerTeam.label })}</span>
        </Meta>
        <EntryScope entry={entry} />
        {entry.active ? (
          <Meta>
            <span>{t('agentAccess.credentials')}</span>
            <span>{summary}</span>
          </Meta>
        ) : (
          <Meta>
            <span>{entry.revokedBy ? t('agentAccess.revokedBy', { date: formatDate(entry.revokedAt ?? entry.createdAt, ctx), name: entry.revokedBy.name }) : t('agentAccess.revokedOn', { date: formatDate(entry.revokedAt ?? entry.createdAt, ctx) })}</span>
          </Meta>
        )}
      </div>
    </Row>
  );
}

export function AccessScreen() {
  const t = useT();
  const entries = useAccessEntries();
  const orgReach = useOrgReach();
  const [registering, setRegistering] = useState(false);
  const [registered, setRegistered] = useState(false);

  const register = () => {
    setRegistered(false);
    setRegistering(true);
  };

  return (
    <>
      <PageHead kicker={t('nav.admin')} title={t('adminAgents.title')} actions={<Button onClick={register}>{t('agentAccess.register')}</Button>} />
      <AgentsTabs current="access" />
      <p className="mb-4 text-muted">{t('agentAccess.lede')}</p>
      <ReachLine orgReach={orgReach} />
      {registered ? <StatusLine tone="positive">{t('agentAccess.registered')}</StatusLine> : null}
      {registering ? (
        <EntryDialog
          open
          onClose={() => setRegistering(false)}
          onSaved={() => {
            setRegistering(false);
            setRegistered(true);
          }}
        />
      ) : null}
      {entries.isPending ? (
        <LoadingState />
      ) : entries.isError ? (
        <ErrorState title={t('agentAccess.errorTitle')} onRetry={() => void entries.refetch()} />
      ) : entries.data.items.length === 0 ? (
        <EmptyState title={t('agentAccess.emptyTitle')} body={t('agentAccess.emptyBody')} />
      ) : (
        <Rows data-access-list="">
          {entries.data.items.map((entry) => (
            <EntryRow key={entry.id} entry={entry} orgReach={orgReach} />
          ))}
        </Rows>
      )}
      <p className="mt-2 text-meta text-muted">{t('agentAccess.registerHint')}</p>
    </>
  );
}
