// The support access feature's names (TEN-06, D-49): aliases over the
// generated schemas in src/types/api.generated.ts.

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type SupportAccessGrant = Schemas['SupportAccessGrant'];
export type SupportAccessPage = Schemas['SupportAccessPage'];
export type SupportAccessState = SupportAccessGrant['state'];
