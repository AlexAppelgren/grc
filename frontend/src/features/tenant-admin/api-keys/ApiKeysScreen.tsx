'use client';

import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ProblemAlert, QueryState, StatusLine } from '@/components/ui/States';
import { ConfirmDialog } from '@/components/ui/Dialogs';
import { SecretOnce } from '@/components/ui/SecretOnce';
import { useFormatContext } from '@/features/identity/hooks';
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from '@/features/tenant-admin/hooks';
import { isExpired, isLive, presentCredential } from '@/features/agent-access/presentation';
import { readsAs } from '@/features/tenant-admin/api-keys/presentation';
import { humaniseKey } from '@/features/tenant-admin/members-presentation';
import type { ApiKey, ApiKeyCreated } from '@/features/tenant-admin/types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// API keys (design/screens/admin-api-keys.html, ID-10, ACC-03): every
// credential of the bank in one list, our integrations' keys, our agent access
// entries' keys and our members' personal tokens, each with its kind and who
// it reads as, and each revocable here without a passkey. Create a key stays an
// integration's key: its plain value appears once, and creating it asks for a
// passkey through the api client's step-up prompt.

// The scopes a bank's key may hold (TENANT_KEY_SCOPES in
// backend/apps/shared/permissions.py), in the design card's order. None
// reaches the library; the watch writes belong to the platform's own agents
// and the server refuses them here. A reference read replaces this list when
// one exists.
export const API_KEY_SCOPES = ['tenant:read', 'library:read', 'upcoming:read', 'search:read', 'proposals:write'] as const;

function scopeDescription(scope: string, t: Translate): string {
  switch (scope) {
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
  return (
    <Panel title={t('admin.apiKeys.newKeyTitle')} role="status" data-new-key="">
      <SecretOnce secret={created.plainKey} copyLabel={t('admin.apiKeys.copy')} onDone={onDone}>
        <p className="text-muted">{t('admin.apiKeys.newKeyBody')}</p>
      </SecretOnce>
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
          <Button variant="outline" onClick={onClose} disabled={create.isPending}>
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
  const [revoked, setRevoked] = useState(false);
  const now = new Date();
  const prefix = `cw_${apiKey.keyPrefix}…`;
  const person = apiKey.person;
  const facts = [
    t('admin.apiKeys.created', { date: formatDate(apiKey.createdAt, ctx) }),
    ...(apiKey.expiresAt !== null ? [isExpired(apiKey, now) ? t('admin.apiKeys.expiredOn', { date: formatDate(apiKey.expiresAt, ctx) }) : t('admin.apiKeys.expires', { date: formatDate(apiKey.expiresAt, ctx) })] : []),
    apiKey.lastUsedAt === null ? t('admin.apiKeys.neverUsed') : t('admin.apiKeys.lastUsed', { date: formatDateTime(apiKey.lastUsedAt, ctx) }),
    ...(apiKey.revokedAt !== null ? [t('admin.apiKeys.revokedOn', { date: formatDate(apiKey.revokedAt, ctx) })] : []),
  ];
  return (
    <Row data-key-id={apiKey.id} data-key-kind={apiKey.kind}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{apiKey.name}</h3>
      </div>
      <Meta>
        <span>{readsAs(apiKey, t)}</span>
        <code className="font-mono">{prefix}</code>
      </Meta>
      <div className="mt-2">
        <PillRow pills={presentCredential(apiKey, t, now)} />
      </div>
      <Meta className="mt-1">{facts.join(' · ')}</Meta>
      {revoked ? <StatusLine>{person === null ? t('admin.apiKeys.revokedDone') : t('admin.credentials.tokenRevoked')}</StatusLine> : null}
      {isLive(apiKey, now) ? (
        <ButtonBar>
          <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
            {t('common.revoke')}
          </Button>
        </ButtonBar>
      ) : null}
      {confirming ? (
        <ConfirmDialog
          title={person === null ? t('admin.credentials.revokeKeyTitle', { name: apiKey.name }) : t('admin.credentials.revokeTokenTitle', { person: person.name, name: apiKey.name })}
          body={person === null ? t('admin.credentials.revokeKeyBody') : t('admin.credentials.revokeTokenBody', { person: person.name })}
          action={person === null ? t('admin.credentials.revokeKey') : t('admin.credentials.revokeToken')}
          cancelLabel={t('common.keep')}
          danger
          busy={revoke.isPending}
          error={revoke.error}
          onConfirm={() =>
            revoke.mutate(apiKey.id, {
              onSuccess: () => {
                setConfirming(false);
                setRevoked(true);
              },
            })
          }
          onClose={() => setConfirming(false)}
        />
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
      <PageHead title={t('admin.apiKeys.title')} lede={t('admin.credentials.lede')} actions={<Button onClick={() => setCreating(true)}>{t('admin.apiKeys.create')}</Button>} />
      {created !== null ? <NewKeyPanel created={created} onDone={() => setCreated(null)} /> : null}
      {creating ? <CreateForm onCreated={setCreated} onClose={() => setCreating(false)} /> : null}
      <QueryState query={keys} errorTitle={t('admin.apiKeys.errorTitle')}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title={t('admin.apiKeys.emptyTitle')} body={t('admin.credentials.emptyBody')} />
          ) : (
            <Rows data-keys-list="">
              {data.items.map((apiKey) => (
                <KeyRow key={apiKey.id} apiKey={apiKey} />
              ))}
            </Rows>
          )
        }
      </QueryState>
    </>
  );
}
