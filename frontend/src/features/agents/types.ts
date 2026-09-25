// The agents feature's names for the chunk 11 contract (AGT-01 to AGT-05, ADM-02).
// Every shape is an alias over the generated schemas in src/types/api.generated.ts;
// the fixed kinds a screen branches on are read off those schemas, never restated.

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

// The platform's definitions and their versions (console, `agent_definitions.manage`).
export type AgentDefinition = Schemas['AgentDefinitionOut'];
export type AgentDefinitionPage = Schemas['AgentDefinitionPage'];
export type AgentDefinitionDetail = Schemas['AgentDefinitionDetail'];
export type AgentVersion = Schemas['AgentVersionOut'];
export type AgentVersionInput = Schemas['AgentVersionInput'];
export type PlatformAgentSettings = Schemas['PlatformAgentSettings'];
export type PlatformAgentSettingsInput = Schemas['PlatformAgentSettingsInput'];
export type RetagRequestInput = Schemas['RetagRequestInput'];

// Runs, the platform's and a bank's alike.
export type AgentRun = Schemas['AgentRunListItem'];
export type AgentRunPage = Schemas['AgentRunListPage'];
export type AgentRunStats = Schemas['AgentRunStats'];

// A bank's own agents, its cap and its research requests (`agents.manage`).
export type TenantAgent = Schemas['TenantAgentOut'];
export type TenantAgentPage = Schemas['TenantAgentPage'];
export type TenantAgentInput = Schemas['TenantAgentInput'];
export type TenantAgentUpdate = Schemas['TenantAgentUpdate'];
export type TenantAgentScope = Schemas['TenantAgentScope'];
export type AgentBudget = Schemas['AgentBudget'];
export type AgentBudgetInput = Schemas['AgentBudgetInput'];
export type ResearchRequest = Schemas['ResearchRequestOut'];
export type ResearchRequestPage = Schemas['ResearchRequestPage'];
export type ResearchRequestInput = Schemas['ResearchRequestInput'];
export type PlatformWatchItem = Schemas['PlatformWatchItem'];
export type PlatformWatchPage = Schemas['PlatformWatchPage'];

export type DefinitionScopeKind = AgentDefinition['scope'];
export type AgentCadence = PlatformAgentSettings['cadence'];
export type RunTrigger = AgentRun['trigger'];
export type ResearchRequestState = ResearchRequest['status'];
export type ResearchRequestKind = ResearchRequest['kind'];

/** A page request: the routes default to 20 and refuse more than 100. */
export interface PageParams {
  limit?: number;
  offset?: number;
}

/** The run list's own filters, on top of a page. */
export interface RunQuery extends PageParams {
  tenantAgentId?: string;
  mine?: boolean;
}
