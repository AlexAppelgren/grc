// The personal tokens feature's names for the ACC-03 contract: aliases over the
// generated schemas in src/types/api.generated.ts.

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type PersonalToken = Schemas['PersonalTokenOut'];
export type PersonalTokensPage = Schemas['PersonalTokensPage'];
export type PersonalTokenCreate = Schemas['PersonalTokenCreate'];
export type PersonalTokenCreated = Schemas['PersonalTokenCreated'];
