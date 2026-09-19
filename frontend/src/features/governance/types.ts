// The audit log's screen model. The wire shapes are the generated
// components['schemas'][…] (src/types/api.generated.ts, from openapi.json);
// nothing is reshaped here, because the log is a ledger: the screen shows
// what the row holds.

import type { Page, PageQuery } from '@/features/tenant-admin/types';
import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type { Page, PageQuery };

/** Who did it: a user, an agent or the system. `id` is empty for the system. */
export type AuditActor = Schemas['AuditActorRef'];

/** The audited record's fields at the time, keyed by field name. */
export type AuditSnapshot = Schemas['AuditSnapshot'];

export type AuditEvent = Schemas['AuditEventRow'];

/** The filters of GET /audit-events. A record is `subjectType` and `subjectId`; `from` is inclusive and `to` exclusive. */
export interface AuditFilters {
  subjectType?: string;
  subjectId?: string;
  actorId?: string;
  from?: string;
  to?: string;
}

export type AuditQuery = AuditFilters & PageQuery;
