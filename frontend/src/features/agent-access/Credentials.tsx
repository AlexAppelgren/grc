'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useCreateKey, useRevokeKey } from '@/features/agent-access/hooks';
import { isExpired, isLive, presentCredential, refusals, scopeLabel } from '@/features/agent-access/presentation';
import type { AccessEntry, AccessKey, AccessKeyCreated } from '@/features/agent-access/types';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// An entry's credentials (design/screens/admin-agent-access.html, states 6
// and 9 to 12; ACC-01, ACC-03). A key holds the four read scopes only and
// lives at most as long as the platform allows; its plain value shows once,
// straight after issuing. Issuing and revoking ask for a passkey.

// The scopes an entry's key may hold (the server refuses any other with
// unknown_key), in the design card's order.
export const ENTRY_KEY_SCOPES = ['library:read', 'search:read', 'upcoming:read', 'tenant:read'] as const;

const SCOPE_HINT: Record<(typeof ENTRY_KEY_SCOPES)[number], MessageKey> = {
  'library:read': 'agentAccess.issue.scope.library:read',
  'search:read': 'agentAccess.issue.scope.search:read',
  'upcoming:read': 'agentAccess.issue.scope.upcoming:read',
  'tenant:read': 'agentAccess.issue.scope.tenant:read',
};

function NewKey({ created, onDone }: { created: AccessKeyCreated; onDone: () => void }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(created.plainKey);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Panel title={t('agentAccess.newKey.title')} role="status" data-new-key="">
      <pre className="m-0 mb-3 rounded-control border border-line bg-subtle p-3 font-mono break-all whitespace-pre-wrap" data-plain-key="">
        {created.plainKey}
      </pre>
      <p className="text-muted">{t('agentAccess.newKey.body')}</p>
      {copied ? <StatusLine tone="positive">{t('agentAccess.newKey.copied')}</StatusLine> : null}
      <ButtonBar>
        <Button variant="outline" size="small" onClick={onDone}>
          {t('common.done')}
        </Button>
        <Button size="small" onClick={() => void copy()}>
          {t('agentAccess.newKey.copy')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

function IssueDialog({ entry, onClose, onIssued }: { entry: AccessEntry; onClose: () => void; onIssued: (key: AccessKeyCreated) => void }) {
  const t = useT();
  const create = useCreateKey(entry.id);
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [expires, setExpires] = useState('');
  const [problem, setProblem] = useState<'name' | 'scopes' | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    const missing = trimmed === '' ? 'name' : scopes.length === 0 ? 'scopes' : null;
    setProblem(missing);
    if (missing !== null) return;
    // A date is the last day the key works, to its end in UTC; none is the longest allowed.
    create.mutate({ name: trimmed, scopes, expiresAt: expires === '' ? null : `${expires}T23:59:59Z` }, { onSuccess: onIssued });
  };

  return (
    <Modal open onOpenChange={(next) => (next ? undefined : onClose())} title={t('agentAccess.issue.title', { name: entry.name })}>
      <form onSubmit={submit} noValidate aria-busy={create.isPending} data-issue-form="">
        <Field id="issue-name" label={t('agentAccess.issue.name')} hint={t('agentAccess.issue.nameHint')} error={problem === 'name' ? t('agentAccess.issue.nameRequired') : undefined}>
          <TextInput id="issue-name" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} aria-invalid={problem === 'name' ? true : undefined} />
        </Field>
        <CheckGroup legend={t('agentAccess.issue.scopes')} error={problem === 'scopes' ? t('agentAccess.issue.scopesRequired') : undefined}>
          {ENTRY_KEY_SCOPES.map((scope) => (
            <CheckRow
              key={scope}
              id={`issue-scope-${scope}`}
              label={scopeLabel(scope)}
              hint={t(SCOPE_HINT[scope])}
              checked={scopes.includes(scope)}
              onChange={(on) => setScopes((current) => (on ? [...current, scope] : current.filter((s) => s !== scope)))}
            />
          ))}
        </CheckGroup>
        <Field id="issue-expires" label={t('agentAccess.issue.expires')} hint={t('agentAccess.issue.expiresHint')}>
          <TextInput id="issue-expires" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
        </Field>
        {create.isError ? <ProblemAlert error={create.error} codes={refusals(t)} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={create.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('agentAccess.issue.submit')}
          </Button>
        </ButtonBar>
        <p className="mt-2 text-meta text-muted">{t('agentAccess.issue.stepUpHint')}</p>
      </form>
    </Modal>
  );
}

function KeyRow({ entryId, apiKey, canRevoke }: { entryId: string; apiKey: AccessKey; canRevoke: boolean }) {
  const t = useT();
  const ctx = useFormatContext();
  const revoke = useRevokeKey(entryId);
  const [confirming, setConfirming] = useState(false);
  const now = new Date();
  const prefix = `cw_${apiKey.keyPrefix}…`;
  const facts = [
    t('agentAccess.keys.issued', { date: formatDate(apiKey.createdAt, ctx) }),
    ...(apiKey.expiresAt ? [isExpired(apiKey, now) ? t('agentAccess.keys.expiredOn', { date: formatDate(apiKey.expiresAt, ctx) }) : t('agentAccess.keys.expires', { date: formatDate(apiKey.expiresAt, ctx) })] : []),
    ...(apiKey.revokedAt ? [t('agentAccess.keys.revokedOn', { date: formatDate(apiKey.revokedAt, ctx) })] : []),
    apiKey.lastUsedAt ? t('agentAccess.lastUsed', { date: formatDateTime(apiKey.lastUsedAt, ctx) }) : t('agentAccess.neverUsed'),
  ];
  return (
    <Row data-key-id={apiKey.id}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{apiKey.name}</h3>
        <PillRow pills={presentCredential(apiKey, t, now)} />
      </div>
      <Meta>
        <code className="font-mono">{prefix}</code>
        {apiKey.person ? <span>{t('agentAccess.keys.actsAs', { name: apiKey.person.name })}</span> : null}
      </Meta>
      <Meta className="mt-1">{facts.join(' · ')}</Meta>
      {canRevoke && isLive(apiKey, now) ? (
        <ButtonBar>
          <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
            {t('agentAccess.keys.revoke')}
          </Button>
        </ButtonBar>
      ) : null}
      {confirming ? (
        <Modal open onOpenChange={(next) => (next ? undefined : setConfirming(false))} title={t('agentAccess.keys.revokeTitle', { name: apiKey.name })} description={t('agentAccess.keys.revokeBody')}>
          {revoke.isError ? <ProblemAlert error={revoke.error} codes={refusals(t)} /> : null}
          <ButtonBar>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={revoke.isPending}>
              {t('agentAccess.keys.keep')}
            </Button>
            <Button variant="danger" disabled={revoke.isPending} onClick={() => revoke.mutate(apiKey.id, { onSuccess: () => setConfirming(false) })}>
              {t('agentAccess.keys.revokeConfirm')}
            </Button>
          </ButtonBar>
          <p className="mt-2 text-meta text-muted">{t('agentAccess.keys.stepUpHint')}</p>
        </Modal>
      ) : null}
    </Row>
  );
}

export function Credentials({ entry }: { entry: AccessEntry }) {
  const t = useT();
  const [issuing, setIssuing] = useState(false);
  const [created, setCreated] = useState<AccessKeyCreated | null>(null);
  return (
    <Panel title={t('agentAccess.keys.title')} data-credentials="">
      <p className="mb-3 text-muted">{t('agentAccess.keys.lede')}</p>
      {created !== null ? <NewKey created={created} onDone={() => setCreated(null)} /> : null}
      {entry.keys.length === 0 ? (
        <p className="text-muted">{t('agentAccess.keys.empty')}</p>
      ) : (
        <Rows data-keys-list="">
          {entry.keys.map((key) => (
            <KeyRow key={key.id} entryId={entry.id} apiKey={key} canRevoke={entry.active} />
          ))}
        </Rows>
      )}
      {entry.active ? (
        <ButtonBar>
          <Button onClick={() => setIssuing(true)}>{t('agentAccess.keys.issue')}</Button>
        </ButtonBar>
      ) : null}
      {issuing ? (
        <IssueDialog
          entry={entry}
          onClose={() => setIssuing(false)}
          onIssued={(key) => {
            setIssuing(false);
            setCreated(key);
          }}
        />
      ) : null}
    </Panel>
  );
}
