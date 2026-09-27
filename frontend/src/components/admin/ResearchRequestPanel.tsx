'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';

import { bankAgentKeys, bankAgentName, refusals } from '@/components/admin/admin-agents';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { createResearchRequest } from '@/features/agents/api';
import type { ResearchRequestInput, TenantAgent } from '@/features/agents/types';
import { consoleSourceKeys, listSources } from '@/features/console-watch/sources';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';

// Ask one of our agents (AGT-05): check a registered source now, check a web
// address, or research a topic. A request is a job: it is queued and the list
// below reads its status from the server. The server's refusals render from
// their codes, among them `no_tenant_agent`, `plan_limit_reached` and
// `budget_cap_reached`.

type AskKind = Extract<ResearchRequestInput['kind'], 'check_source' | 'check_url' | 'research_topic'>;

const ASK_KINDS = {
  check_source: 'adminAgents.research.kind.checkSource',
  check_url: 'adminAgents.research.kind.checkUrl',
  research_topic: 'adminAgents.research.kind.researchTopic',
} as const satisfies Record<AskKind, MessageKey>;

interface Draft {
  kind: AskKind;
  tenantAgentId: string;
  sourceId: string;
  url: string;
  topic: string;
}

/** The request body for the chosen kind, or which field is missing. Only the kind's own field is sent. */
export function requestBody(draft: Draft): ResearchRequestInput | 'source' | 'url' | 'topic' {
  const base = { kind: draft.kind, tenantAgentId: draft.tenantAgentId };
  if (draft.kind === 'check_source') return draft.sourceId === '' ? 'source' : { ...base, sourceId: draft.sourceId };
  if (draft.kind === 'check_url') return /^https:\/\/\S+$/.test(draft.url.trim()) ? { ...base, url: draft.url.trim() } : 'url';
  return draft.topic.trim() === '' ? 'topic' : { ...base, topic: draft.topic.trim() };
}

export function ResearchRequestPanel({ agents }: { agents: readonly TenantAgent[] }) {
  const t = useT();
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: consoleSourceKeys.sources, queryFn: listSources });
  const [draft, setDraft] = useState<Draft>({ kind: 'check_source', tenantAgentId: agents[0]?.id ?? '', sourceId: '', url: '', topic: '' });
  const [missing, setMissing] = useState<'source' | 'url' | 'topic' | null>(null);
  const ask = useMutation({
    mutationFn: createResearchRequest,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: bankAgentKeys.requests });
      setDraft((d) => ({ ...d, url: '', topic: '' }));
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body = requestBody(draft);
    if (typeof body === 'string') return setMissing(body);
    setMissing(null);
    ask.mutate(body);
  };

  return (
    <Panel title={t('adminAgents.research.title')} data-research-panel="">
      <p className="-mt-1.5 mb-3 text-meta text-muted">{t('adminAgents.research.lede')}</p>
      <form onSubmit={submit} noValidate aria-busy={ask.isPending}>
        <fieldset className="mb-3 flex flex-wrap gap-x-4 gap-y-1 border-0 p-0">
          <legend className="mb-1 font-medium">{t('adminAgents.research.what')}</legend>
          {(Object.keys(ASK_KINDS) as AskKind[]).map((kind) => (
            <label key={kind} className="flex items-center gap-2">
              <input type="radio" name="research-kind" className="size-4 accent-button" value={kind} checked={draft.kind === kind} onChange={() => setDraft({ ...draft, kind })} />
              {t(ASK_KINDS[kind])}
            </label>
          ))}
        </fieldset>
        <Field id="research-agent" label={t('adminAgents.research.agent')}>
          <Select id="research-agent" value={draft.tenantAgentId} onChange={(e) => setDraft({ ...draft, tenantAgentId: e.target.value })}>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {bankAgentName(agent.agent, t)}
              </option>
            ))}
          </Select>
        </Field>
        {draft.kind === 'check_source' ? (
          <Field id="research-source" label={t('adminAgents.research.source')} error={missing === 'source' ? t('adminAgents.research.sourceRequired') : undefined}>
            <Select id="research-source" value={draft.sourceId} onChange={(e) => setDraft({ ...draft, sourceId: e.target.value })}>
              <option value="">{t('adminAgents.research.sourcePick')}</option>
              {(sources.data ?? []).filter((source) => source.active).map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        {draft.kind === 'check_url' ? (
          <Field id="research-url" label={t('adminAgents.research.url')} hint={t('adminAgents.research.urlHint')} error={missing === 'url' ? t('adminAgents.research.urlRequired') : undefined}>
            <TextInput id="research-url" type="url" inputMode="url" maxLength={2000} value={draft.url} onChange={(e) => setDraft({ ...draft, url: e.target.value })} />
          </Field>
        ) : null}
        {draft.kind === 'research_topic' ? (
          <Field id="research-topic" label={t('adminAgents.research.topic')} hint={t('adminAgents.research.topicHint')} error={missing === 'topic' ? t('adminAgents.research.topicRequired') : undefined}>
            <TextArea id="research-topic" rows={2} value={draft.topic} onChange={(e) => setDraft({ ...draft, topic: e.target.value })} />
          </Field>
        ) : null}
        {ask.isError ? <ProblemAlert error={ask.error} codes={refusals(t)} /> : null}
        {ask.isSuccess ? <StatusLine tone="positive">{t('adminAgents.research.asked')}</StatusLine> : null}
        <ButtonBar>
          <Button type="submit" disabled={ask.isPending}>
            {t('adminAgents.research.submit')}
          </Button>
        </ButtonBar>
      </form>
    </Panel>
  );
}
