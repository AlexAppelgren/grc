import { api } from '@/shared/utils/api-client';

import type { AiGeneration, AiLogQuery, AuditEvent, AuditQuery, Page } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). The audit log is the
// governance app's tenant route (AUD-01), and the AI log beside it (AUD-02).

const AUDIT_EVENTS = '/api/v1/audit-events';

export async function listAuditEvents(query: AuditQuery): Promise<Page<AuditEvent>> {
  return (await api.get<Page<AuditEvent>>(AUDIT_EVENTS, { params: query })).data;
}

const AI_GENERATIONS = '/api/v1/ai-generations';

export async function listAiGenerations(query: AiLogQuery): Promise<Page<AiGeneration>> {
  return (await api.get<Page<AiGeneration>>(AI_GENERATIONS, { params: query })).data;
}
