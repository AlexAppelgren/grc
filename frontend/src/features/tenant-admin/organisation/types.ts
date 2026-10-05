import type { components } from '@/types/api.generated';

// The organisation screen's records (TEN-02), as the tenants routes send and
// take them (backend/apps/tenants/schemas.py). The wire shapes are already
// what the screen reads, so they are named here rather than copied.

type Schemas = components['schemas'];

export type OrgUnit = Schemas['TenantOrgUnit'];
/** A unit as `GET /tenant/org-units` lists it: a legal entity carries its licences. */
export type OrgUnitRow = Schemas['TenantOrgUnitRow'];
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

/** A lookup in the public registers (TEN-07): a job, and once it succeeded the companies it found. */
export type RegisterLookup = Schemas['RegisterLookupOut'];
export type RegisterLookupEntity = Schemas['RegisterLookupEntity'];
export type RegisterApply = Schemas['RegisterApplyOut'];
/** What a supervisor's register says about one legal entity, with where and when it was read. */
export type RegisterEntry = Schemas['TenantRegisterEntry'];
/** A library authority, for the name of the register a company was looked up in. */
export type Authority = Schemas['LibraryAuthority'];

/** A write that changes an existing row carries the version it was read at (If-Match). */
export interface VersionedPatch<T> {
  id: string;
  body: T;
  version: number;
}
