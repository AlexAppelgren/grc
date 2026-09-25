// My work (HOM-05, D-23): GET /me/work. Every shape is an alias over the
// generated schemas; nothing is reshaped here.

import type { components, operations } from '@/types/api.generated';

type Schemas = components['schemas'];

export type WorkPage = Schemas['HomeWorkPage'];
export type WorkItem = Schemas['HomeWorkItem'];
export type WorkReason = Schemas['HomeWorkReason'];
export type WorkBucket = WorkItem['bucket'];
export type WorkItemKind = WorkItem['itemKind'];
export type WorkDate = NonNullable<WorkItem['date']>;
export type WorkCounts = Schemas['HomeWorkCounts'];
export type WorkQuery = NonNullable<operations['getMyWork']['parameters']['query']>;

/** Whose work the page shows: the reader's own, or one department's. */
export type WorkScope = { scope: 'mine' } | { scope: 'unit'; unit: string };
