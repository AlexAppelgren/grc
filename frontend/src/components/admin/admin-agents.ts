import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { definitionName } from '@/features/agents/agents-presentation';
import { getAgentBudget, listTenantAgents, MAX_PAGE } from '@/features/agents/api';
import type { AgentBudget, TenantAgent, TenantAgentPage } from '@/features/agents/types';
import type { Market } from '@/features/footprint/types';
import { localeTags, type Locale, type MessageKey, type Translate } from '@/shared/i18n';

// What the panels of /admin/agents share (design/screens/admin-agents.html):
// their query keys, how a refusal reads from its `code`, the spend meter's
// figure, when an agent next runs and the order its markets are offered in.
// The agents feature is only imported here, never edited (R2 plan).

export const bankAgentKeys = {
  all: ['tenant', 'agents'] as const,
  list: ['tenant', 'agents', 'list'] as const,
  runs: (tenantAgentId: string) => ['tenant', 'agents', 'runs', tenantAgentId] as const,
  platform: ['tenant', 'agents', 'platform'] as const,
  budget: ['tenant', 'agents', 'budget'] as const,
  requests: ['tenant', 'agents', 'requests'] as const,
  request: (requestId: string) => ['tenant', 'agents', 'requests', requestId] as const,
};

/** The bank's own agents: a plan allows a handful, so one page at the route's maximum holds them. */
export function useBankAgents(enabled: boolean): UseQueryResult<TenantAgentPage> {
  return useQuery({ queryKey: bankAgentKeys.list, queryFn: () => listTenantAgents({ limit: MAX_PAGE, offset: 0 }), enabled });
}

export function useBankBudget(enabled: boolean): UseQueryResult<AgentBudget> {
  return useQuery({ queryKey: bankAgentKeys.budget, queryFn: getAgentBudget, enabled });
}

/** How many runs each agent's "Recent runs" shows; older ones stay in the route's history. */
export const RECENT_RUNS = 5;

// Every refusal the agent routes answer, read from its code, never its detail.
const REFUSAL_KEY = {
  above_plan_limit: 'adminAgents.refusal.abovePlanLimit',
  unknown_key: 'adminAgents.refusal.unknownKey',
  duplicate_key: 'adminAgents.refusal.duplicateKey',
  no_tenant_agent: 'adminAgents.refusal.noTenantAgent',
  plan_limit_reached: 'adminAgents.refusal.planLimitReached',
  budget_cap_reached: 'adminAgents.refusal.budgetCapReached',
  budget_cap_required: 'adminAgents.refusal.budgetCapRequired',
  agent_paused: 'adminAgents.refusal.agentPaused',
  agent_disabled: 'adminAgents.refusal.agentDisabled',
  feature_off: 'adminAgents.refusal.featureOff',
  run_finished: 'adminAgents.refusal.runFinished',
  step_up_required: 'problem.stepUpCancelled',
} as const satisfies Record<string, MessageKey>;

export type RefusalCode = keyof typeof REFUSAL_KEY;

/** The sentence each refusal code renders in place, for `ProblemAlert`'s `codes`. */
export function refusals(t: Translate): Record<RefusalCode, string> {
  return Object.fromEntries(Object.entries(REFUSAL_KEY).map(([code, key]) => [code, t(key)])) as Record<RefusalCode, string>;
}

// The tenant-scoped definitions a bank may add. No route lists them to a
// bank, so the catalog names the ones bleqq ships; the server refuses any
// other key with `unknown_key` and one of bleqq's own with a 403.
export const ADDABLE_DEFINITIONS = {
  'tenant-source-watch': { name: 'adminAgents.definition.sourceWatch.name', what: 'adminAgents.definition.sourceWatch.what' },
  'scope-researcher': { name: 'adminAgents.definition.scopeResearcher.name', what: 'adminAgents.definition.scopeResearcher.what' },
} as const satisfies Record<string, { name: MessageKey; what: MessageKey }>;

type AddableKey = keyof typeof ADDABLE_DEFINITIONS;

function isAddable(agentKey: string): agentKey is AddableKey {
  return Object.hasOwn(ADDABLE_DEFINITIONS, agentKey);
}

/** A bank's agent is named by its definition: the catalog's words, else its key read as words. */
export function bankAgentName(agentKey: string, t: Translate): string {
  return isAddable(agentKey) ? t(ADDABLE_DEFINITIONS[agentKey].name) : definitionName(agentKey);
}

export function bankAgentWhat(agentKey: string, t: Translate): string | null {
  return isAddable(agentKey) ? t(ADDABLE_DEFINITIONS[agentKey].what) : null;
}

export interface Spend {
  spent: number;
  cap: number | null;
  /** Whole percent of the cap spent, at most 100; null with no cap, so no meter is drawn. */
  percent: number | null;
  reached: boolean;
}

/** The month's spend against the cap. Without a cap there is no meter, never an empty one. */
export function spendOf(budget: Pick<AgentBudget, 'monthlyCap' | 'spentThisMonth'>): Spend {
  const spent = Number(budget.spentThisMonth);
  if (budget.monthlyCap === null) return { spent, cap: null, percent: null, reached: false };
  const cap = Number(budget.monthlyCap);
  const reached = spent >= cap;
  return { spent, cap, percent: reached ? 100 : Math.min(100, Math.round((spent / cap) * 100)), reached };
}

export type NextRun =
  | { kind: 'off' | 'paused' | 'capPaused' | 'aiOff' | 'capReached' | 'manual' | 'unscheduled' }
  | { kind: 'at'; at: string };

/**
 * When an agent next runs, from its own facts and the organisation's: off and
 * paused first, then what holds every agent (the AI switch, the cap), then
 * its cadence. A pause nobody made is the cap's.
 */
export function nextRunOf(agent: Pick<TenantAgent, 'enabled' | 'pausedAt' | 'pausedBy' | 'cadence' | 'nextRunAt'>, org: { aiEnabled: boolean; capReached: boolean }): NextRun {
  if (!agent.enabled) return { kind: 'off' };
  if (agent.pausedAt !== null) return { kind: agent.pausedBy === null ? 'capPaused' : 'paused' };
  if (!org.aiEnabled) return { kind: 'aiOff' };
  if (org.capReached) return { kind: 'capReached' };
  if (agent.cadence === 'manual') return { kind: 'manual' };
  return agent.nextRunAt === null ? { kind: 'unscheduled' } : { kind: 'at', at: agent.nextRunAt };
}

export const NEXT_RUN_KEY = {
  off: 'adminAgents.next.off',
  paused: 'adminAgents.next.paused',
  capPaused: 'adminAgents.next.capPaused',
  aiOff: 'adminAgents.next.aiOff',
  capReached: 'adminAgents.next.capReached',
  manual: 'adminAgents.next.manual',
  unscheduled: 'adminAgents.next.unscheduled',
} as const satisfies Record<Exclude<NextRun['kind'], 'at'>, MessageKey>;

/** The markets an agent may cover: the operating ones first, then the watched ones. */
export function scopeMarkets(markets: readonly Market[]): Market[] {
  return [...markets.filter((m) => m.level === 'operating'), ...markets.filter((m) => m.level === 'watching')];
}

/** A cap as the route takes it: euro with at most two decimals, or null when it is not one. */
export function parseCap(value: string): string | null {
  const trimmed = value.trim().replace(',', '.');
  return /^\d{1,8}(\.\d{1,2})?$/.test(trimmed) ? trimmed : null;
}

/** 1 is Monday and 7 Sunday, as the route counts them. */
export const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;
export const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

/** A run day in the reader's language: 1 January 2024 was a Monday. */
export function weekdayLabel(weekday: number, locale: Locale): string {
  return new Intl.DateTimeFormat(localeTags[locale], { weekday: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2024, 0, weekday)));
}

/** A run hour on the 24-hour clock the Nordics read: 6 is "06:00". */
export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`;
}
