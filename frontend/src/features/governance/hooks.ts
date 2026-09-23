'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import * as governance from '@/features/governance/api';
import type { AiGeneration, AiLogQuery, AuditEvent, AuditQuery, Page } from '@/features/governance/types';

// Query keys for the audit log and the AI log (playbook 6.1). Nothing here writes, so there
// is nothing to invalidate: the log is append-only and read on demand.

export const governanceKeys = {
  auditEvents: (query: AuditQuery) => ['audit-events', query] as const,
  aiGenerations: (query: AiLogQuery) => ['ai-generations', query] as const,
};

export const AUDIT_LOG_PAGE = 20;

export function useAuditEvents(query: AuditQuery): UseQueryResult<Page<AuditEvent>> {
  return useQuery({
    queryKey: governanceKeys.auditEvents(query),
    queryFn: () => governance.listAuditEvents(query),
    // A filter change keeps the previous page on screen instead of flashing
    // the loading state under the filters the person is still adjusting.
    placeholderData: (previous) => previous,
  });
}

export const AI_LOG_PAGE = 20;

export function useAiGenerations(query: AiLogQuery): UseQueryResult<Page<AiGeneration>> {
  return useQuery({
    queryKey: governanceKeys.aiGenerations(query),
    queryFn: () => governance.listAiGenerations(query),
    placeholderData: (previous) => previous,
  });
}
