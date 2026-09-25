import type { components } from '@/types/api.generated';

// The organisation screen's records (TEN-02), as the tenants routes send and
// take them (backend/apps/tenants/schemas.py). The wire shapes are already
// what the screen reads, so they are named here rather than copied.

type Schemas = components['schemas'];

export type OrgUnit = Schemas['TenantOrgUnit'];
export type OrgUnitKind = OrgUnit['kind'];
export type OrgUnitBody = Schemas['TenantOrgUnitBody'];
export type OrgUnitPatch = Schemas['TenantOrgUnitPatch'];

export type Licence = Schemas['TenantLicence'];
export type LicenceBody = Schemas['TenantLicenceBody'];
export type LicencePatch = Schemas['TenantLicencePatch'];

export type Product = Schemas['TenantProductOut'];
export type ProductStatus = Product['status'];
export type ProductBody = Schemas['TenantProductBody'];
export type ProductPatch = Schemas['TenantProductPatch'];

export type PersonRef = Schemas['PersonRef'];

/** A write that changes an existing row carries the version it was read at (If-Match). */
export interface VersionedPatch<T> {
  id: string;
  body: T;
  version: number;
}
