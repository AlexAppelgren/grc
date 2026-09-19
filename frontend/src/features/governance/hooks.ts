'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import * as governance from '@/features/governance/api';
import type { AuditEvent, AuditQuery, Page } from '@/features/governance/types';

// Query keys for the audit log (playbook 6.1). Nothing here writes, so there
// is nothing to invalidate: the log is append-only and read on demand.

export const governanceKeys = {
  auditEvents: (query: AuditQuery) => ['audit-events', query] as const,
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
