'use client';

import { useQuery } from '@tanstack/react-query';

import { bankAgentKeys, bankAgentName } from '@/components/admin/admin-agents';
import { EmptyState } from '@/components/ui/EmptyState';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { presentResearchRequest } from '@/features/agents/agents-presentation';
import { getResearchRequest, listResearchRequests } from '@/features/agents/api';
import type { ResearchRequest, ResearchRequestState, TenantAgent } from '@/features/agents/types';
import { useFormatContext } from '@/features/identity/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// Our research requests (AGT-05), newest first. A request still queued or
// running is re-read from its own status endpoint until it settles; the
// client never works a status out for itself.

/** How often an open request is re-read, in milliseconds (`NEXT_PUBLIC_RESEARCH_POLL_MS`). */
export const RESEARCH_POLL_MS = Number(process.env.NEXT_PUBLIC_RESEARCH_POLL_MS ?? 5000);

const SHOWN = 20;

export function isOpen(status: ResearchRequestState): boolean {
  return status === 'queued' || status === 'running';
}

const KIND_KEY = {
  run_now: 'adminAgents.research.kind.runNow',
  check_source: 'adminAgents.research.kind.checkSource',
  check_url: 'adminAgents.research.kind.checkUrl',
  research_topic: 'adminAgents.research.kind.researchTopic',
  retag: 'adminAgents.research.kind.retag',
} as const satisfies Record<ResearchRequest['kind'], MessageKey>;

function RequestRow({ listed, agents }: { listed: ResearchRequest; agents: readonly TenantAgent[] }) {
  const t = useT();
  const ctx = useFormatContext();
  const polled = useQuery({
    queryKey: bankAgentKeys.request(listed.id),
    queryFn: () => getResearchRequest(listed.id),
    enabled: isOpen(listed.status),
    refetchInterval: (query) => (query.state.data === undefined || isOpen(query.state.data.status) ? RESEARCH_POLL_MS : false),
  });
  const request = polled.data ?? listed;
  const agent = agents.find((a) => a.id === request.tenantAgentId);
  const target = request.topic ?? request.url;
  const facts = [
    agent === undefined ? null : bankAgentName(agent.agent, t),
    t('adminAgents.research.by', { name: request.requestedBy.name, date: formatDateTime(request.createdAt, ctx) }),
  ].filter((fact): fact is string => fact !== null);

  return (
    <Row data-research-request={request.id} data-request-status={request.status}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{t(KIND_KEY[request.kind])}</h3>
        <PillRow pills={[presentResearchRequest(request, t)]} />
      </div>
      {target === null ? null : <p className="mt-1 break-words">{target}</p>}
      <p className="mt-1 text-meta text-muted">{facts.join(' · ')}</p>
    </Row>
  );
}

export function ResearchRequestList({ agents }: { agents: readonly TenantAgent[] }) {
  const t = useT();
  const requests = useQuery({ queryKey: bankAgentKeys.requests, queryFn: () => listResearchRequests({ limit: SHOWN, offset: 0 }) });

  return (
    <Panel title={t('adminAgents.research.listTitle')} data-research-list="">
      {requests.isPending ? (
        <LoadingState rows={1} />
      ) : requests.isError ? (
        <ErrorState title={t('adminAgents.research.errorTitle')} onRetry={() => void requests.refetch()} />
      ) : requests.data.items.length === 0 ? (
        <EmptyState title={t('adminAgents.research.emptyTitle')} body={t('adminAgents.research.emptyBody')} />
      ) : (
        <Rows>
          {requests.data.items.map((request) => (
            <RequestRow key={request.id} listed={request} agents={agents} />
          ))}
        </Rows>
      )}
    </Panel>
  );
}
