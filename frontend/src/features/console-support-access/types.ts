// The console's support access names (TEN-06, D-49): aliases over the
// generated schemas in src/types/api.generated.ts.

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type ConsoleSupportGrant = Schemas['ConsoleSupportAccessGrant'];
export type ConsoleSupportGrantPage = Schemas['ConsoleSupportAccessPage'];
export type ConsoleSupportRequest = Schemas['ConsoleSupportAccessBody'];
export type SupportSessionTokens = Schemas['SessionTokens'];
