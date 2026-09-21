'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import {
  AGENT_KEY_SCOPES,
  isLive,
  presentAgentKey,
  useAgentKeys,
  useCreateAgentKey,
  useRevokeAgentKey,
  type AgentKey,
  type AgentKeyCreated,
} from '@/features/console-watch/agent-keys';
import { useFormatContext } from '@/features/identity/hooks';
import { humaniseKey } from '@/features/tenant-admin/members-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// Agent keys (design/screens/console-agent-keys.html, ID-10, AGT-01): the keys
// bleqq's own agents run on, each bound to the agent everything it writes is
// recorded as. Creating one asks for a passkey, which the api client's step-up
// prompt drives off the server's own `step_up_required`.
//
// The plain key is shown once and never again. It lives in this component's
// state for the one render and reaches no storage, no URL, no log line and no
// query cache; the screen says so where it shows it, and offers nothing that
// would claim to show it later.

function NewKeyPanel({ created, onDone }: { created: AgentKeyCreated; onDone: () => void }) {
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
    <Panel title={t('console.agentKeys.secretTitle')} role="status" data-new-key="">
      <pre className="m-0 mb-3 rounded-control border border-line bg-subtle p-3 font-mono break-all whitespace-pre-wrap" data-plain-key="">
        {created.plainKey}
      </pre>
      <p className="text-muted">{t('console.agentKeys.secretBody')}</p>
      <p className="text-meta text-muted">{t('console.agentKeys.secretOnce')}</p>
      {copied ? <StatusLine tone="positive">{t('console.agentKeys.copied')}</StatusLine> : null}
      <ButtonBar>
        <Button variant="outline" size="small" onClick={onDone}>
          {t('common.done')}
        </Button>
        <Button size="small" onClick={() => void copy()}>
          {t('console.agentKeys.copy')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

type FormProblem = 'name' | 'agent' | 'scopes';

function CreateKeyModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (key: AgentKeyCreated) => void }) {
  const t = useT();
  const create = useCreateAgentKey();
  const [name, setName] = useState('');
  const [agentId, setAgentId] = useState('');
  const [expires, setExpires] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [problem, setProblem] = useState<FormProblem | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim() === '') return setProblem('name');
    if (agentId.trim() === '') return setProblem('agent');
    if (scopes.length === 0) return setProblem('scopes');
    setProblem(null);
    create.mutate(
      { name: name.trim(), agentId: agentId.trim(), scopes, ...(expires === '' ? {} : { expiresAt: `${expires}T23:59:59Z` }) },
      {
        onSuccess: (key) => {
          onCreated(key);
          setName('');
          setAgentId('');
          setExpires('');
          setScopes([]);
          onClose();
        },
      },
    );
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={t('console.agentKeys.createTitle')} description={t('console.agentKeys.stepUpNote')}>
      <form onSubmit={submit} noValidate aria-busy={create.isPending} data-agent-key-form="">
        <Field id="agent-key-name" label={t('console.agentKeys.name')} hint={t('console.agentKeys.nameHint')} error={problem === 'name' ? t('console.agentKeys.nameRequired') : undefined}>
          <TextInput id="agent-key-name" value={name} placeholder={t('console.agentKeys.namePlaceholder')} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid gap-x-4 md:grid-cols-2">
          {/* The agent is named by its id: the platform's agent definitions
              have no read of their own yet, so there is no list to pick from. */}
          <Field id="agent-key-agent" label={t('console.agentKeys.agent')} hint={t('console.agentKeys.agentHint')} error={problem === 'agent' ? t('console.agentKeys.agentRequired') : undefined}>
            <TextInput id="agent-key-agent" value={agentId} placeholder={t('console.agentKeys.agentIdPlaceholder')} onChange={(e) => setAgentId(e.target.value)} />
          </Field>
          <Field id="agent-key-expires" label={t('console.agentKeys.expiresLabel')} hint={t('console.agentKeys.expiresHint')}>
            <TextInput id="agent-key-expires" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
        </div>
        <CheckGroup legend={t('console.agentKeys.scopes')} hint={t('console.agentKeys.scopesHint')} error={problem === 'scopes' ? t('console.agentKeys.scopesRequired') : undefined}>
          {AGENT_KEY_SCOPES.map((scope) => (
            <CheckRow
              key={scope}
              id={`agent-scope-${scope}`}
              label={humaniseKey(scope)}
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
            {t('console.agentKeys.createAction')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function KeyRow({ agentKey, now }: { agentKey: AgentKey; now: Date }) {
  const t = useT();
  const ctx = useFormatContext();
  const revoke = useRevokeAgentKey();
  const [confirming, setConfirming] = useState(false);
  return (
    <Row data-agent-key-id={agentKey.id}>
      <h3 className="mb-1 font-semibold">{agentKey.name}</h3>
      <Meta>
        <code className="font-mono">{t('console.agentKeys.keyPrefix', { prefix: agentKey.keyPrefix })}</code>
        <span>{formatDateTime(agentKey.createdAt, ctx)}</span>
        <span>{agentKey.lastUsedAt === null ? t('console.agentKeys.state.neverUsed') : t('console.agentKeys.lastUsed', { date: formatDateTime(agentKey.lastUsedAt, ctx) })}</span>
        <span>{agentKey.expiresAt === null ? t('console.agentKeys.noExpiry') : t('console.agentKeys.expires', { date: formatDate(agentKey.expiresAt, ctx) })}</span>
        {agentKey.revokedAt === null ? null : <span>{t('console.agentKeys.revokedBy', { date: formatDateTime(agentKey.revokedAt, ctx), name: agentKey.agent?.label ?? '' })}</span>}
      </Meta>
      <div className="mt-2">
        <PillRow pills={presentAgentKey(agentKey, t, now)} />
      </div>
      {revoke.isError ? <ProblemAlert error={revoke.error} /> : null}
      {confirming ? <StatusLine>{t('console.agentKeys.revokeBody')}</StatusLine> : null}
      {isLive(agentKey, now) ? (
        <ButtonBar>
          {confirming ? (
            <>
              <Button variant="outline" size="small" onClick={() => setConfirming(false)}>
                {t('common.cancel')}
              </Button>
              <Button variant="danger" size="small" disabled={revoke.isPending} onClick={() => revoke.mutate(agentKey.id, { onSettled: () => setConfirming(false) })}>
                {t('console.agentKeys.revokeAction')}
              </Button>
            </>
          ) : (
            <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
              {t('console.agentKeys.revoke')}
            </Button>
          )}
        </ButtonBar>
      ) : null}
    </Row>
  );
}

export function AgentKeysScreen() {
  const t = useT();
  const keys = useAgentKeys();
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<AgentKeyCreated | null>(null);
  const now = new Date();

  return (
    <>
      <PageHead title={t('console.agentKeys.title')} lede={t('console.agentKeys.lede')} actions={<Button onClick={() => setCreating(true)}>{t('console.agentKeys.create')}</Button>} />
      {created !== null ? <NewKeyPanel created={created} onDone={() => setCreated(null)} /> : null}
      {keys.isPending ? (
        <LoadingState rows={3} />
      ) : keys.isError ? (
        <ErrorState title={t('console.agentKeys.errorTitle')} onRetry={() => void keys.refetch()} />
      ) : keys.data.items.length === 0 ? (
        <EmptyState title={t('console.agentKeys.emptyTitle')} body={t('console.agentKeys.emptyBody')} />
      ) : (
        <Rows data-agent-keys-list="">
          {keys.data.items.map((agentKey) => (
            <KeyRow key={agentKey.id} agentKey={agentKey} now={now} />
          ))}
        </Rows>
      )}
      <CreateKeyModal open={creating} onClose={() => setCreating(false)} onCreated={setCreated} />
    </>
  );
}
