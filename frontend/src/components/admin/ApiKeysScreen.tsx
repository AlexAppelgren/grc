'use client';

import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from '@/features/tenant-admin/hooks';
import { humaniseKey, presentApiKey } from '@/features/tenant-admin/members-presentation';
import type { ApiKey, ApiKeyCreated } from '@/features/tenant-admin/types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// API keys (design/screens/admin-api-keys.html, ID-10): the plain key
// appears once, straight after creation, and never again. Creation asks
// for a passkey through the api client's step-up prompt.

// The scope constants of backend/apps/shared/permissions.py. None reaches
// the library. A reference read replaces this list when one exists.
export const API_KEY_SCOPES = ['agent-runs:write', 'sources:write', 'changes:write', 'proposals:write', 'search:read', 'library:read', 'upcoming:read', 'tenant:read'] as const;

function scopeDescription(scope: string, t: Translate): string {
  switch (scope) {
    case 'agent-runs:write':
      return t('admin.apiKeys.scope.agent-runs:write');
    case 'sources:write':
      return t('admin.apiKeys.scope.sources:write');
    case 'changes:write':
      return t('admin.apiKeys.scope.changes:write');
    case 'proposals:write':
      return t('admin.apiKeys.scope.proposals:write');
    case 'search:read':
      return t('admin.apiKeys.scope.search:read');
    case 'library:read':
      return t('admin.apiKeys.scope.library:read');
    case 'upcoming:read':
      return t('admin.apiKeys.scope.upcoming:read');
    case 'tenant:read':
      return t('admin.apiKeys.scope.tenant:read');
    default:
      return humaniseKey(scope);
  }
}

function NewKeyPanel({ created, onDone }: { created: ApiKeyCreated; onDone: () => void }) {
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
    <Panel sand title={t('admin.apiKeys.newKeyTitle')} role="status" data-new-key="">
      <pre className="m-0 mb-2.5 rounded-s border border-line bg-surface p-3.5 font-mono whitespace-pre-wrap break-all" data-plain-key="">
        {created.plainKey}
      </pre>
      <p className="text-muted">{t('admin.apiKeys.newKeyBody')}</p>
      {copied ? <StatusLine tone="positive">{t('admin.apiKeys.copied')}</StatusLine> : null}
      <ButtonBar>
        <Button variant="ghost" size="small" onClick={onDone}>
          {t('common.done')}
        </Button>
        <Button size="small" onClick={() => void copy()}>
          {t('admin.apiKeys.copy')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

function CreateForm({ onCreated, onClose }: { onCreated: (key: ApiKeyCreated) => void; onClose: () => void }) {
  const t = useT();
  const create = useCreateApiKey();
  const [name, setName] = useState('');
  const [expires, setExpires] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [problem, setProblem] = useState<'name' | 'scopes' | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim() === '') {
      setProblem('name');
      return;
    }
    if (scopes.length === 0) {
      setProblem('scopes');
      return;
    }
    setProblem(null);
    create.mutate(
      { name: name.trim(), scopes, ...(expires === '' ? {} : { expiresAt: `${expires}T23:59:59Z` }) },
      {
        onSuccess: (key) => {
          onCreated(key);
          onClose();
        },
      },
    );
  };

  return (
    <form onSubmit={submit} noValidate aria-busy={create.isPending}>
      <Panel title={t('admin.apiKeys.create')} data-key-form="">
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="key-name" label={t('admin.apiKeys.name')} error={problem === 'name' ? t('admin.apiKeys.nameRequired') : undefined}>
            <TextInput id="key-name" placeholder={t('admin.apiKeys.namePlaceholder')} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field id="key-expires" label={t('admin.apiKeys.expiresField')} hint={t('admin.apiKeys.expiresHint')}>
            <TextInput id="key-expires" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
        </div>
        <CheckGroup legend={t('admin.apiKeys.scopes')} hint={t('admin.apiKeys.stepUp')} error={problem === 'scopes' ? t('admin.apiKeys.scopesRequired') : undefined}>
          {API_KEY_SCOPES.map((scope) => (
            <CheckRow
              key={scope}
              id={`key-scope-${scope}`}
              label={humaniseKey(scope)}
              hint={scopeDescription(scope, t)}
              checked={scopes.includes(scope)}
              onChange={(checked) => setScopes((current) => (checked ? [...current, scope] : current.filter((k) => k !== scope)))}
            />
          ))}
        </CheckGroup>
        {create.isError ? <ProblemAlert error={create.error} codes={{ step_up_required: t('problem.stepUpCancelled') }} /> : null}
        <ButtonBar>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('admin.apiKeys.createButton')}
          </Button>
        </ButtonBar>
      </Panel>
    </form>
  );
}

function KeyRow({ apiKey }: { apiKey: ApiKey }) {
  const t = useT();
  const ctx = useFormatContext();
  const revoke = useRevokeApiKey();
  const [confirming, setConfirming] = useState(false);
  const now = new Date();
  const live = apiKey.revokedAt === null && (apiKey.expiresAt === null || new Date(apiKey.expiresAt) > now);
  const prefix = `${apiKey.keyPrefix}…`;
  return (
    <Row data-key-id={apiKey.id}>
      <h3 className="mb-1 font-semibold">{apiKey.name}</h3>
      <Meta>
        <code className="font-mono">{prefix}</code>
        <span>{t('admin.apiKeys.created', { date: formatDateTime(apiKey.createdAt, ctx) })}</span>
        {apiKey.expiresAt !== null ? (
          <span>{new Date(apiKey.expiresAt) > now ? t('admin.apiKeys.expires', { date: formatDate(apiKey.expiresAt, ctx) }) : t('admin.apiKeys.expiredOn', { date: formatDate(apiKey.expiresAt, ctx) })}</span>
        ) : null}
        <span>{apiKey.lastUsedAt === null ? t('admin.apiKeys.neverUsed') : t('admin.apiKeys.lastUsed', { date: formatDateTime(apiKey.lastUsedAt, ctx) })}</span>
        {apiKey.revokedAt !== null ? <span>{t('admin.apiKeys.revokedOn', { date: formatDateTime(apiKey.revokedAt, ctx) })}</span> : null}
      </Meta>
      <div className="mt-2">
        <PillRow pills={presentApiKey(apiKey, t, now)} />
      </div>
      {revoke.isError ? <ProblemAlert error={revoke.error} /> : null}
      {confirming ? <StatusLine>{t('admin.apiKeys.revokeConfirm')}</StatusLine> : null}
      {live ? (
        <ButtonBar>
          {confirming ? (
            <>
              <Button variant="ghost" size="small" onClick={() => setConfirming(false)}>
                {t('common.cancel')}
              </Button>
              <Button variant="danger" size="small" disabled={revoke.isPending} onClick={() => revoke.mutate(apiKey.id, { onSettled: () => setConfirming(false) })}>
                {t('admin.apiKeys.revoke')}
              </Button>
            </>
          ) : (
            <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
              {t('admin.apiKeys.revoke')}
            </Button>
          )}
        </ButtonBar>
      ) : null}
    </Row>
  );
}

export function ApiKeysScreen() {
  const t = useT();
  const keys = useApiKeys();
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.apiKeys.title')} lede={t('admin.apiKeys.lede')} actions={<Button onClick={() => setCreating(true)}>{t('admin.apiKeys.create')}</Button>} />
      {created !== null ? <NewKeyPanel created={created} onDone={() => setCreated(null)} /> : null}
      {creating ? <CreateForm onCreated={setCreated} onClose={() => setCreating(false)} /> : null}
      {keys.isPending ? (
        <LoadingState />
      ) : keys.isError ? (
        <ErrorState title={t('admin.apiKeys.errorTitle')} onRetry={() => void keys.refetch()} />
      ) : keys.data.items.length === 0 ? (
        <EmptyState title={t('admin.apiKeys.emptyTitle')} body={t('admin.apiKeys.emptyBody')} />
      ) : (
        <Rows data-keys-list="">
          {keys.data.items.map((apiKey) => (
            <KeyRow key={apiKey.id} apiKey={apiKey} />
          ))}
        </Rows>
      )}
    </>
  );
}
