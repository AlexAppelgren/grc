import type {
  AgentBudget,
  AgentBudgetInput,
  AgentDefinitionDetail,
  AgentDefinitionPage,
  AgentRun,
  AgentRunPage,
  AgentVersion,
  AgentVersionInput,
  PageParams,
  PlatformAgentSettings,
  PlatformAgentSettingsInput,
  PlatformWatchPage,
  ResearchRequest,
  ResearchRequestInput,
  ResearchRequestPage,
  RetagRequestInput,
  RunQuery,
  TenantAgent,
  TenantAgentInput,
  TenantAgentPage,
  TenantAgentUpdate,
} from '@/features/agents/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1) over every operation a
// person's session makes on the agents app. The run writes an agent makes with
// its own key (`startAgentRun`, `finishAgentRun`) are not here: no session can
// make them. Step-up is the api client's: a 403 `step_up_required` runs the
// passkey and retries once, so publishing, retiring and a platform settings
// change need nothing of their own here.

const V1 = '/api/v1';
const DEFINITIONS = `${V1}/agent-definitions`;
const TENANT_AGENTS = `${V1}/agents`;
const RESEARCH = `${V1}/research-requests`;

/** The routes' maximum page, where a screen wants one page to hold everything. */
export const MAX_PAGE = 100;

const segment = (value: string | number) => encodeURIComponent(String(value));

// ---------------------------------------------------------------------------
// The console: the platform's definitions, versions, settings and runs
// ---------------------------------------------------------------------------

/** The platform ships a handful of agents; one page at the route's maximum holds them all. */
export async function listAgentDefinitions(): Promise<AgentDefinitionPage> {
  return (await api.get<AgentDefinitionPage>(DEFINITIONS, { params: { limit: MAX_PAGE, offset: 0 } })).data;
}

export async function getAgentDefinition(agentKey: string): Promise<AgentDefinitionDetail> {
  return (await api.get<AgentDefinitionDetail>(`${DEFINITIONS}/${segment(agentKey)}`)).data;
}

export async function publishAgentVersion(agentKey: string, body: AgentVersionInput): Promise<AgentVersion> {
  return (await api.post<AgentVersion>(`${DEFINITIONS}/${segment(agentKey)}/versions`, body)).data;
}

export async function retireAgentVersion(agentKey: string, versionNo: number): Promise<AgentVersion> {
  return (await api.post<AgentVersion>(`${DEFINITIONS}/${segment(agentKey)}/versions/${segment(versionNo)}/retire`, {})).data;
}

export async function getPlatformAgentSettings(agentKey: string): Promise<PlatformAgentSettings> {
  return (await api.get<PlatformAgentSettings>(`${DEFINITIONS}/${segment(agentKey)}/settings`)).data;
}

export async function updatePlatformAgentSettings(agentKey: string, body: PlatformAgentSettingsInput): Promise<PlatformAgentSettings> {
  return (await api.put<PlatformAgentSettings>(`${DEFINITIONS}/${segment(agentKey)}/settings`, body)).data;
}

export async function listPlatformRuns(page: PageParams = {}): Promise<AgentRunPage> {
  return (await api.get<AgentRunPage>(`${V1}/console/agent-runs`, { params: page })).data;
}

/**
 * The newest runs of bleqq's own agents. The route answers oldest first, so
 * the newest page sits at the end: one small read learns the total, and the
 * second reads the last page at the route's maximum.
 */
export async function listRecentPlatformRuns(): Promise<AgentRunPage> {
  const { total } = await listPlatformRuns({ limit: 1, offset: 0 });
  return listPlatformRuns({ limit: MAX_PAGE, offset: Math.max(total - MAX_PAGE, 0) });
}

export async function createRetagRequest(body: RetagRequestInput): Promise<ResearchRequest> {
  return (await api.post<ResearchRequest>(`${V1}/console/research-requests`, body)).data;
}

// ---------------------------------------------------------------------------
// A bank: what bleqq watches, its own agents, their runs, its cap and requests
// ---------------------------------------------------------------------------

export async function listPlatformWatch(page: PageParams = {}): Promise<PlatformWatchPage> {
  return (await api.get<PlatformWatchPage>(`${TENANT_AGENTS}/platform`, { params: page })).data;
}

export async function listTenantAgents(page: PageParams = {}): Promise<TenantAgentPage> {
  return (await api.get<TenantAgentPage>(TENANT_AGENTS, { params: page })).data;
}

export async function createTenantAgent(body: TenantAgentInput): Promise<TenantAgent> {
  return (await api.post<TenantAgent>(TENANT_AGENTS, body)).data;
}

export async function updateTenantAgent(tenantAgentId: string, body: TenantAgentUpdate): Promise<TenantAgent> {
  return (await api.patch<TenantAgent>(`${TENANT_AGENTS}/${segment(tenantAgentId)}`, body)).data;
}

export async function runTenantAgentNow(tenantAgentId: string): Promise<AgentRun> {
  return (await api.post<AgentRun>(`${TENANT_AGENTS}/${segment(tenantAgentId)}/runs`, {})).data;
}

export async function pauseTenantAgent(tenantAgentId: string): Promise<TenantAgent> {
  return (await api.post<TenantAgent>(`${TENANT_AGENTS}/${segment(tenantAgentId)}/pause`, {})).data;
}

export async function resumeTenantAgent(tenantAgentId: string): Promise<TenantAgent> {
  return (await api.delete<TenantAgent>(`${TENANT_AGENTS}/${segment(tenantAgentId)}/pause`)).data;
}

/** The runs a session may see: a bank's own and the platform's library runs, or the console's. */
export async function listAgentRuns(query: RunQuery = {}): Promise<AgentRunPage> {
  return (await api.get<AgentRunPage>(`${V1}/agent-runs`, { params: query })).data;
}

export async function interruptAgentRun(runId: string): Promise<AgentRun> {
  return (await api.post<AgentRun>(`${V1}/agent-runs/${segment(runId)}/interrupt`, {})).data;
}

export async function getAgentBudget(): Promise<AgentBudget> {
  return (await api.get<AgentBudget>(`${V1}/tenant/agent-budget`)).data;
}

export async function putAgentBudget(body: AgentBudgetInput): Promise<AgentBudget> {
  return (await api.put<AgentBudget>(`${V1}/tenant/agent-budget`, body)).data;
}

export async function listResearchRequests(page: PageParams = {}): Promise<ResearchRequestPage> {
  return (await api.get<ResearchRequestPage>(RESEARCH, { params: page })).data;
}

export async function createResearchRequest(body: ResearchRequestInput): Promise<ResearchRequest> {
  return (await api.post<ResearchRequest>(RESEARCH, body)).data;
}

export async function getResearchRequest(requestId: string): Promise<ResearchRequest> {
  return (await api.get<ResearchRequest>(`${RESEARCH}/${segment(requestId)}`)).data;
}
