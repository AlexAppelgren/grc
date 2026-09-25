import type { AgentCadence, AgentDefinition, AgentRun, AgentVersion, ResearchRequest, TenantAgent } from '@/features/agents/types';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import {
  agentDefinitionScopeTone,
  agentDefinitionStateTone,
  agentRunStateTone,
  agentVersionStateTone,
  researchRequestStateTone,
  slotTone,
  tenantAgentStateTone,
  type AgentDefinitionStateKind,
  type AgentRunStateKind,
  type AgentVersionStateKind,
  type ResearchRequestStateKind,
  type TenantAgentStateKind,
} from '@/features/shared/tone-by-kind';
import { localeTags, type MessageKey, type Translate } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';

// How an agent, a definition, a version, a run and a research request read
// (design/system/pills-and-labels.md, "Chunk 11"). Every pill's tone comes
// from tone-by-kind.ts by the record's own facts; no screen picks one.

export const AGENT_SLOT_ORDER = {
  scope: 10,
  version: 20,
  state: 30,
} as const;

// ---------------------------------------------------------------------------
// States, each read off the record's own facts
// ---------------------------------------------------------------------------

/** A person's stop reads as stopped whatever the run then closed into. */
export function runStateOf(run: Pick<AgentRun, 'status' | 'interruptedAt'>): AgentRunStateKind {
  if (run.interruptedAt !== null) return 'stopped';
  if (run.status === 'running') return 'running';
  return run.status === 'succeeded' ? 'done' : 'failed';
}

/** Paused is a person's hold and wins over the switch; off is the switch alone. */
export function tenantAgentStateOf(agent: Pick<TenantAgent, 'enabled' | 'pausedAt'>): TenantAgentStateKind {
  if (agent.pausedAt !== null) return 'paused';
  return agent.enabled ? 'on' : 'off';
}

export function definitionStateOf(definition: Pick<AgentDefinition, 'active'>): AgentDefinitionStateKind {
  return definition.active ? 'active' : 'draft';
}

/** The current version and a retired one say so; an earlier live one needs no pill. */
export function versionStateOf(version: Pick<AgentVersion, 'versionNo' | 'retiredAt'>, currentVersion: number): AgentVersionStateKind | null {
  if (version.retiredAt !== null) return 'retired';
  return version.versionNo === currentVersion ? 'current' : null;
}

/** Only an earlier version still live may be retired: a newer version replaces the current one. */
export function canRetire(version: Pick<AgentVersion, 'versionNo' | 'retiredAt'>, currentVersion: number): boolean {
  return versionStateOf(version, currentVersion) === null;
}

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

const RUN_STATE_KEY = {
  done: 'agents.run.done',
  running: 'agents.run.running',
  stopped: 'agents.run.stopped',
  failed: 'agents.run.failed',
} as const satisfies Record<AgentRunStateKind, MessageKey>;

const TENANT_AGENT_STATE_KEY = {
  on: 'agents.state.on',
  paused: 'agents.state.paused',
  off: 'agents.state.off',
} as const satisfies Record<TenantAgentStateKind, MessageKey>;

const SCOPE_KEY = {
  platform: 'agents.scope.platform',
  tenant: 'agents.scope.tenant',
} as const satisfies Record<AgentDefinition['scope'], MessageKey>;

const DEFINITION_STATE_KEY = {
  active: 'agents.definition.active',
  draft: 'agents.definition.draft',
} as const satisfies Record<AgentDefinitionStateKind, MessageKey>;

const VERSION_STATE_KEY = {
  current: 'agents.version.current',
  retired: 'agents.version.retired',
} as const satisfies Record<AgentVersionStateKind, MessageKey>;

const REQUEST_STATE_KEY = {
  queued: 'agents.request.queued',
  running: 'agents.request.running',
  done: 'agents.request.done',
  failed: 'agents.request.failed',
  rejected: 'agents.request.rejected',
  cancelled: 'agents.request.cancelled',
} as const satisfies Record<ResearchRequestStateKind, MessageKey>;

export const CADENCE_KEY = {
  daily: 'agents.cadence.daily',
  weekly: 'agents.cadence.weekly',
  monthly: 'agents.cadence.monthly',
  manual: 'agents.cadence.manual',
} as const satisfies Record<AgentCadence, MessageKey>;

export const TRIGGER_KEY = {
  schedule: 'agents.trigger.schedule',
  manual: 'agents.trigger.manual',
  request: 'agents.trigger.request',
  api: 'agents.trigger.api',
} as const satisfies Record<AgentRun['trigger'], MessageKey>;

// ---------------------------------------------------------------------------
// Pills
// ---------------------------------------------------------------------------

export function presentDefinition(definition: AgentDefinition, t: Translate): PresentedPill[] {
  const state = definitionStateOf(definition);
  const pills: PresentedPill[] = [
    { key: `scope:${definition.scope}`, label: t(SCOPE_KEY[definition.scope]), tone: agentDefinitionScopeTone[definition.scope], order: AGENT_SLOT_ORDER.scope },
    { key: `state:${state}`, label: t(DEFINITION_STATE_KEY[state]), tone: agentDefinitionStateTone[state], order: AGENT_SLOT_ORDER.state },
  ];
  // A draft has no version to name yet.
  if (state === 'active') {
    pills.push({ key: 'version', label: t('agents.versionNo', { version: definition.currentVersion }), tone: slotTone.agentVersion, order: AGENT_SLOT_ORDER.version });
  }
  return pills.sort(byOrder);
}

export function presentVersion(version: AgentVersion, currentVersion: number, t: Translate): PresentedPill[] {
  const state = versionStateOf(version, currentVersion);
  return state === null ? [] : [{ key: `state:${state}`, label: t(VERSION_STATE_KEY[state]), tone: agentVersionStateTone[state], order: AGENT_SLOT_ORDER.state }];
}

export function presentRunState(run: Pick<AgentRun, 'status' | 'interruptedAt'>, t: Translate): PresentedPill {
  const state = runStateOf(run);
  return { key: `run:${state}`, label: t(RUN_STATE_KEY[state]), tone: agentRunStateTone[state], order: AGENT_SLOT_ORDER.state };
}

export function presentTenantAgentState(agent: Pick<TenantAgent, 'enabled' | 'pausedAt'>, t: Translate): PresentedPill {
  const state = tenantAgentStateOf(agent);
  return { key: `state:${state}`, label: t(TENANT_AGENT_STATE_KEY[state]), tone: tenantAgentStateTone[state], order: AGENT_SLOT_ORDER.state };
}

export function presentResearchRequest(request: Pick<ResearchRequest, 'status'>, t: Translate): PresentedPill {
  return { key: `request:${request.status}`, label: t(REQUEST_STATE_KEY[request.status]), tone: researchRequestStateTone[request.status], order: AGENT_SLOT_ORDER.state };
}

/** A jurisdiction an agent sweeps is a scope facet: brand, by its slot. */
export function presentJurisdictions(keys: readonly string[], labelOf: (key: string) => string): PresentedPill[] {
  return keys.map((key, i) => ({ key: `jurisdiction:${key}`, label: labelOf(key), tone: slotTone.jurisdiction, order: i }));
}

// ---------------------------------------------------------------------------
// Figures
// ---------------------------------------------------------------------------

/** A decimal string from the API, in euro and the reader's language; null while nothing was reported. */
export function formatEuro(value: string | null, ctx: Pick<FormatContext, 'locale'>): string | null {
  if (value === null) return null;
  return new Intl.NumberFormat(localeTags[ctx.locale], { style: 'currency', currency: 'EUR' }).format(Number(value));
}

/** Whole minutes a closed run took, at least one; null while it runs. */
export function runMinutes(run: Pick<AgentRun, 'startedAt' | 'finishedAt'>): number | null {
  if (run.finishedAt === null) return null;
  return Math.max(1, Math.round((new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime()) / 60_000));
}

/** A definition is named by its stable key, read as words: `watch-sweeper` is "Watch sweeper". */
export function definitionName(agentKey: string): string {
  const words = agentKey.replace(/[._:-]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
