'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { apiKeyStateTone, slotTone, type ApiKeyStateKind } from '@/features/shared/tone-by-kind';
import { humaniseKey } from '@/features/tenant-admin/members-presentation';
import type { MessageKey, Translate } from '@/shared/i18n';
import { api } from '@/shared/utils/api-client';
import type { components } from '@/types/api.generated';

// Platform agent keys (ID-10, AGT-01, ADM-02): the keys bleqq's own research
// agents run on. They are the platform's alone — the agents are platform-owned
// and platform-run — so no tenant route reaches them and no key here carries a
// scope that writes to the library: an agent proposes, and a library editor
// approves.
//
// The plain key exists for exactly one render. It is never put in a query
// cache, in storage, in a URL or in a log line, which is why it is returned to
// the caller and held in component state rather than kept by a hook.

type Schemas = components['schemas'];

export type AgentKey = Schemas['AgentKeyOut'];
export type AgentKeyPage = Schemas['AgentKeysPage'];
export type AgentKeyCreate = Schemas['AgentKeyCreate'];
export type AgentKeyCreated = Schemas['AgentKeyCreated'];
export type AgentDefinition = Schemas['AgentDefinitionOut'];
export type AgentDefinitionPage = Schemas['AgentDefinitionPage'];

const AGENT_KEYS = '/api/v1/agent-keys';
const AGENT_DEFINITIONS = '/api/v1/agent-definitions';

/**
 * The scopes an agent's key may hold. None of them writes to the library
 * (PRO-01): `proposals:review` is the confirming agent's (D-62, D-74), and it
 * approves or rejects through the proposal door and writes nothing else.
 */
export const AGENT_KEY_SCOPES = ['agent-runs:write', 'sources:write', 'changes:write', 'proposals:write', 'proposals:review', 'search:read', 'library:read'] as const;

/** One page at the route's maximum; paging joins the screen when the key list outgrows it. */
export const AGENT_KEYS_PAGE = 100;

export async function listAgentKeys(): Promise<AgentKeyPage> {
  return (await api.get<AgentKeyPage>(AGENT_KEYS, { params: { limit: AGENT_KEYS_PAGE, offset: 0 } })).data;
}

/** The platform ships a handful of agents; one page at the route's maximum holds them all. */
export async function listAgentDefinitions(): Promise<AgentDefinitionPage> {
  return (await api.get<AgentDefinitionPage>(AGENT_DEFINITIONS, { params: { limit: AGENT_KEYS_PAGE, offset: 0 } })).data;
}

export async function createAgentKey(body: AgentKeyCreate): Promise<AgentKeyCreated> {
  return (await api.post<AgentKeyCreated>(AGENT_KEYS, body)).data;
}

export async function revokeAgentKey(keyId: string): Promise<AgentKey> {
  return (await api.post<AgentKey>(`${AGENT_KEYS}/${keyId}/revoke`, {})).data;
}

export const agentKeyKeys = {
  keys: ['console', 'agent-keys'] as const,
  definitions: ['console', 'agent-definitions'] as const,
};

export function useAgentKeys(): UseQueryResult<AgentKeyPage> {
  return useQuery({ queryKey: agentKeyKeys.keys, queryFn: listAgentKeys });
}

export function useAgentDefinitions(): UseQueryResult<AgentDefinitionPage> {
  return useQuery({ queryKey: agentKeyKeys.definitions, queryFn: listAgentDefinitions });
}

export function useCreateAgentKey(): UseMutationResult<AgentKeyCreated, unknown, AgentKeyCreate> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: createAgentKey, onSuccess: () => queryClient.invalidateQueries({ queryKey: agentKeyKeys.keys }) });
}

export function useRevokeAgentKey(): UseMutationResult<AgentKey, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: revokeAgentKey, onSuccess: () => queryClient.invalidateQueries({ queryKey: agentKeyKeys.keys }) });
}

// ---------------------------------------------------------------------------
// Presentation
// ---------------------------------------------------------------------------

export const AGENT_KEY_SLOT_ORDER = {
  state: 10,
  agent: 20,
  scopes: 30,
} as const;

const STATE_KEY = {
  active: 'console.agentKeys.state.active',
  never_used: 'console.agentKeys.state.neverUsed',
  revoked: 'console.agentKeys.state.revoked',
  expired: 'console.agentKeys.state.expired',
} as const satisfies Record<ApiKeyStateKind, MessageKey>;

/**
 * What the key is doing now, computed from its own dates: revoked and expired
 * both mean it has stopped working, and a key nobody has used yet is a neutral
 * fact rather than a healthy one.
 */
export function agentKeyState(key: AgentKey, now: Date): ApiKeyStateKind {
  if (key.revokedAt !== null) return 'revoked';
  if (key.expiresAt !== null && new Date(key.expiresAt).getTime() <= now.getTime()) return 'expired';
  return key.lastUsedAt === null ? 'never_used' : 'active';
}

export function isLive(key: AgentKey, now: Date): boolean {
  const state = agentKeyState(key, now);
  return state !== 'revoked' && state !== 'expired';
}

export function presentAgentKey(key: AgentKey, t: Translate, now: Date): PresentedPill[] {
  const state = agentKeyState(key, now);
  const pills: PresentedPill[] = [
    { key: `state:${state}`, label: t(STATE_KEY[state]), tone: apiKeyStateTone[state], order: AGENT_KEY_SLOT_ORDER.state },
    ...key.scopes.map((scope, i) => ({ key: `scope:${scope}`, label: humaniseKey(scope), tone: slotTone.apiScope, order: AGENT_KEY_SLOT_ORDER.scopes + i })),
  ];
  // Everything the key writes is recorded as this agent, so the binding is a
  // fact of the row and not a detail (AGT-01).
  if (key.agent !== null) {
    pills.push({ key: `agent:${key.agent.key}`, label: key.agent.label, tone: slotTone.agentVersion, order: AGENT_KEY_SLOT_ORDER.agent });
  }
  return pills.sort(byOrder);
}
