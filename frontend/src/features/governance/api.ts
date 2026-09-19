import { api } from '@/shared/utils/api-client';

import type { AuditEvent, AuditQuery, Page } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). The audit log is the
// governance app's one tenant route in this chunk (AUD-01).

const AUDIT_EVENTS = '/api/v1/audit-events';

export async function listAuditEvents(query: AuditQuery): Promise<Page<AuditEvent>> {
  return (await api.get<Page<AuditEvent>>(AUDIT_EVENTS, { params: query })).data;
}
