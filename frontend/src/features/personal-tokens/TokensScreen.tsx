'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, Select, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { isExpired, scopeLabel } from '@/features/agent-access/presentation';
import { useFormatContext } from '@/features/identity/hooks';
import { useCreateMyToken, useMyTokens, useRevokeMyToken, useTokenEntries } from '@/features/personal-tokens/hooks';
import { isLiveToken, mintRefusals, presentToken, SCOPE_HINT, SCOPE_PERMISSION, TOKEN_SCOPES } from '@/features/personal-tokens/presentation';
import type { PersonalToken, PersonalTokenCreated } from '@/features/personal-tokens/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { humanisePermission, usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// My access tokens (design/screens/me-tokens.html, ACC-03): a member mints a
// token that reads as them, behind a passkey, sees it once, lists and revokes
// their own. Without tokens.create there is no Create button, and the tokens
// already held stay listed and revocable. Naming an agent access entry needs
// the entry list, which only agent_access.manage reads.

const TOKENS_CREATE = 'tokens.create';
const AGENT_ACCESS_MANAGE = 'agent_access.manage';

function NewToken({ created, onDone }: { created: PersonalTokenCreated; onDone: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
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
    <Panel title={t('me.tokens.newTitle')} role="status" data-new-key="">
      <pre className="m-0 mb-3 rounded-control border border-line bg-subtle p-3 font-mono break-all whitespace-pre-wrap" data-plain-key="">
        {created.plainKey}
      </pre>
      <p className="text-muted">{t('me.tokens.newBody', { date: formatDate(created.expiresAt, ctx) })}</p>
      {copied ? <StatusLine tone="positive">{t('me.tokens.copied')}</StatusLine> : null}
      <ButtonBar>
        <Button variant="outline" size="small" onClick={onDone}>
          {t('common.done')}
        </Button>
        <Button size="small" onClick={() => void copy()}>
          {t('me.tokens.copy')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

type Problem = 'name' | 'scopes' | 'entry' | 'expires';

function CreateDialog({ permissions, onClose, onCreated }: { permissions: readonly string[]; onClose: () => void; onCreated: (token: PersonalTokenCreated) => void }) {
  const t = useT();
  const create = useCreateMyToken();
  const canNameEntry = permissions.includes(AGENT_ACCESS_MANAGE);
  const entries = useTokenEntries(canNameEntry);
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [entryId, setEntryId] = useState('');
  const [expires, setExpires] = useState('');
  const [problem, setProblem] = useState<Problem | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    const missing: Problem | null =
      trimmed === '' ? 'name' : scopes.length === 0 ? 'scopes' : scopes.includes('tenant:read') && entryId === '' ? 'entry' : expires === '' ? 'expires' : null;
    setProblem(missing);
    if (missing !== null) return;
    // A date is the last day the token works, to its end in UTC.
    create.mutate({ name: trimmed, scopes, expiresAt: `${expires}T23:59:59Z`, agentAccessId: entryId === '' ? null : entryId }, { onSuccess: onCreated });
  };

  const liveEntries = (entries.data?.items ?? []).filter((entry) => entry.active);
  return (
    <Modal open onOpenChange={(next) => (next ? undefined : onClose())} title={t('me.tokens.create')}>
      <form onSubmit={submit} noValidate aria-busy={create.isPending} data-token-form="">
        <Field id="token-name" label={t('me.tokens.name')} hint={t('me.tokens.nameHint')} error={problem === 'name' ? t('me.tokens.nameRequired') : undefined}>
          <TextInput id="token-name" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} aria-invalid={problem === 'name' ? true : undefined} />
        </Field>
        <CheckGroup legend={t('me.tokens.scopes')} hint={t('me.tokens.scopesHint')} error={problem === 'scopes' ? t('me.tokens.scopesRequired') : undefined}>
          {TOKEN_SCOPES.map((scope) => {
            const held = permissions.includes(SCOPE_PERMISSION[scope]);
            // tenant:read reads only through a named entry, which needs the entry list.
            const reachable = scope !== 'tenant:read' || canNameEntry;
            const hint = !held ? t('me.tokens.scopeNotHeld', { permission: humanisePermission(SCOPE_PERMISSION[scope]) }) : reachable ? t(SCOPE_HINT[scope]) : t('me.tokens.entryRequired');
            return (
              <CheckRow
                key={scope}
                id={`token-scope-${scope}`}
                label={scopeLabel(scope)}
                hint={hint}
                checked={scopes.includes(scope)}
                disabled={!held || !reachable}
                onChange={(on) => setScopes((current) => (on ? [...current, scope] : current.filter((s) => s !== scope)))}
              />
            );
          })}
        </CheckGroup>
        {canNameEntry ? (
          <Field id="token-entry" label={t('me.tokens.entry')} hint={t('me.tokens.entryHint')} error={problem === 'entry' ? t('me.tokens.entryRequired') : undefined}>
            <Select id="token-entry" value={entryId} onChange={(e) => setEntryId(e.target.value)}>
              <option value="">{t('me.tokens.entryNone')}</option>
              {liveEntries.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        <Field id="token-expires" label={t('me.tokens.expires')} hint={t('me.tokens.expiresHint')} error={problem === 'expires' ? t('me.tokens.expiresRequired') : undefined}>
          <TextInput id="token-expires" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} aria-invalid={problem === 'expires' ? true : undefined} />
        </Field>
        {create.isError ? <ProblemAlert error={create.error} codes={mintRefusals(t)} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={create.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('me.tokens.submit')}
          </Button>
        </ButtonBar>
        <p className="mt-2 text-meta text-muted">{t('me.tokens.stepUpHint')}</p>
      </form>
    </Modal>
  );
}

function TokenRow({ token }: { token: PersonalToken }) {
  const t = useT();
  const ctx = useFormatContext();
  const revoke = useRevokeMyToken();
  const [confirming, setConfirming] = useState(false);
  const [revoked, setRevoked] = useState(false);
  const now = new Date();
  const prefix = `cw_${token.keyPrefix}…`;
  const facts = [
    t('me.tokens.created', { date: formatDate(token.createdAt, ctx) }),
    isExpired(token, now) ? t('me.tokens.expiredOn', { date: formatDate(token.expiresAt, ctx) }) : t('me.tokens.expiresOn', { date: formatDate(token.expiresAt, ctx) }),
    ...(token.revokedAt !== null ? [t('me.tokens.revokedOn', { date: formatDate(token.revokedAt, ctx) })] : []),
    token.lastUsedAt !== null ? t('me.tokens.lastUsed', { date: formatDateTime(token.lastUsedAt, ctx) }) : t('me.tokens.neverUsed'),
  ];
  return (
    <Row data-token-id={token.id}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{token.name}</h3>
      </div>
      <Meta>
        <code className="font-mono">{prefix}</code>
        <span>{token.agentAccess === null ? t('me.tokens.readsAsMe') : t('me.tokens.readsAsMeWithin', { entry: token.agentAccess.name })}</span>
      </Meta>
      <div className="mt-2">
        <PillRow pills={presentToken(token, t, now)} />
      </div>
      <Meta className="mt-1">{facts.join(' · ')}</Meta>
      {revoked ? <StatusLine>{t('me.tokens.revokedDone')}</StatusLine> : null}
      {isLiveToken(token, now) ? (
        <ButtonBar>
          <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
            {t('me.tokens.revoke')}
          </Button>
        </ButtonBar>
      ) : null}
      {confirming ? (
        <Modal open onOpenChange={(next) => (next ? undefined : setConfirming(false))} title={t('me.tokens.revokeTitle', { name: token.name })} description={t('me.tokens.revokeBody')}>
          {revoke.isError ? <ProblemAlert error={revoke.error} /> : null}
          <ButtonBar>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={revoke.isPending}>
              {t('me.tokens.keep')}
            </Button>
            <Button
              variant="danger"
              disabled={revoke.isPending}
              onClick={() =>
                revoke.mutate(token.id, {
                  onSuccess: () => {
                    setConfirming(false);
                    setRevoked(true);
                  },
                })
              }
            >
              {t('me.tokens.revokeConfirm')}
            </Button>
          </ButtonBar>
        </Modal>
      ) : null}
    </Row>
  );
}

export function TokensScreen() {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const canCreate = permissions.includes(TOKENS_CREATE);
  const tokens = useMyTokens();
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<PersonalTokenCreated | null>(null);
  const open = () => setCreating(true);

  return (
    <>
      <PageHead title={t('me.tokens.title')} lede={t('me.tokens.lede')} actions={canCreate ? <Button onClick={open}>{t('me.tokens.create')}</Button> : undefined} />
      {canCreate ? null : <Notice>{t('me.tokens.cannotCreate', { permission: humanisePermission(TOKENS_CREATE) })}</Notice>}
      {created !== null ? <NewToken created={created} onDone={() => setCreated(null)} /> : null}
      {tokens.isPending ? (
        <LoadingState />
      ) : tokens.isError ? (
        <ErrorState title={t('me.tokens.errorTitle')} onRetry={() => void tokens.refetch()} />
      ) : tokens.data.items.length === 0 ? (
        <EmptyState
          title={t('me.tokens.emptyTitle')}
          body={canCreate ? t('me.tokens.emptyBody') : t('me.tokens.cannotCreate', { permission: humanisePermission(TOKENS_CREATE) })}
          action={canCreate ? { label: t('me.tokens.create'), href: '#', onClick: open } : undefined}
        />
      ) : (
        <Rows data-tokens-list="">
          {tokens.data.items.map((token) => (
            <TokenRow key={token.id} token={token} />
          ))}
        </Rows>
      )}
      {creating ? (
        <CreateDialog
          permissions={permissions}
          onClose={() => setCreating(false)}
          onCreated={(token) => {
            setCreating(false);
            setCreated(token);
          }}
        />
      ) : null}
    </>
  );
}
