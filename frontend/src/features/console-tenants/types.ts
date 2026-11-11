// The console tenants feature's names for the ADM-02 contract. Every shape is
// an alias over the generated schemas in src/types/api.generated.ts (from the
// backend's OpenAPI export; `bash generate-types.sh` regenerates them). A
// local definition remains only where the generator cannot express the shape,
// each with a one-line reason.

import type { components, operations } from '@/types/api.generated';

type Schemas = components['schemas'];

// Local: the backend types the tenant's lifecycle as a plain string; the fixed kind list lives here.
export type TenantStatus = 'active' | 'deactivated';

// Local: the backend types the first administrator's invitation status as a plain string; the fixed kind list lives here.
export type FirstAdministratorStatus = 'pending' | 'expired' | 'accepted' | 'revoked';

export type FirstAdministrator = Omit<Schemas['ConsoleFirstAdministrator'], 'status'> & { status: FirstAdministratorStatus };

export type ConsoleTenant = Omit<Schemas['ConsoleTenantRow'], 'status' | 'firstAdministrator'> & {
  status: TenantStatus;
  firstAdministrator: FirstAdministrator | null;
};
export type ConsoleTenantCreate = Schemas['ConsoleTenantCreateBody'];

// Local: the generator emits one concrete page per item type, never a generic.
export interface ConsoleTenantPage {
  items: ConsoleTenant[];
  total: number;
}

// Partial: `limit` and `offset` have server defaults, which the generator renders as required fields.
export type PageQuery = NonNullable<operations['listMembers']['parameters']['query']>;
