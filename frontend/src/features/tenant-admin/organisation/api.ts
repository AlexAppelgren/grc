import type {
  Authority,
  Licence,
  LicenceBody,
  LicencePatch,
  OrgUnit,
  OrgUnitBody,
  OrgUnitPatch,
  OrgUnitRow,
  PersonRef,
  Product,
  ProductBody,
  ProductPatch,
  RegisterApply,
  RegisterLookup,
} from '@/features/tenant-admin/organisation/types';
import type { Page } from '@/features/tenant-admin/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1) for the organisation
// routes (TEN-02). A change sends the version it was read at as If-Match, so
// a row someone else changed in between is refused with stale_write.

const TENANT = '/api/v1/tenant';
// One page at the server's maximum: a bank's units, each legal entity with its
// licences, and its products are short lists.
const ALL = { limit: 100 };

const id = (value: string) => encodeURIComponent(value);

export async function listOrgUnits(): Promise<OrgUnitRow[]> {
  return (await api.get<Page<OrgUnitRow>>(`${TENANT}/org-units`, { params: ALL })).data.items;
}

export async function createOrgUnit(body: OrgUnitBody): Promise<OrgUnit> {
  return (await api.post<OrgUnit>(`${TENANT}/org-units`, body)).data;
}

export async function updateOrgUnit(unitId: string, body: OrgUnitPatch, version: number): Promise<OrgUnit> {
  return (await api.patch<OrgUnit>(`${TENANT}/org-units/${id(unitId)}`, body, { version })).data;
}

export async function createLicence(unitId: string, body: LicenceBody): Promise<Licence> {
  return (await api.post<Licence>(`${TENANT}/org-units/${id(unitId)}/licences`, body)).data;
}

export async function updateLicence(licenceId: string, body: LicencePatch, version: number): Promise<Licence> {
  return (await api.patch<Licence>(`${TENANT}/licences/${id(licenceId)}`, body, { version })).data;
}

export async function listProducts(): Promise<Product[]> {
  return (await api.get<Page<Product>>(`${TENANT}/products`, { params: ALL })).data.items;
}

export async function createProduct(body: ProductBody): Promise<Product> {
  return (await api.post<Product>(`${TENANT}/products`, body)).data;
}

export async function updateProduct(productId: string, body: ProductPatch, version: number): Promise<Product> {
  return (await api.patch<Product>(`${TENANT}/products/${id(productId)}`, body, { version })).data;
}

/** The bank's active members as ids and names: every owner and head picker reads it. */
export async function listPeople(): Promise<PersonRef[]> {
  return (await api.get<PersonRef[]>('/api/v1/reference/people')).data;
}

/** Starts a lookup in the public registers (202): only the number or LEI leaves the bank. */
export async function startRegisterLookup(query: string): Promise<RegisterLookup> {
  return (await api.post<RegisterLookup>(`${TENANT}/register-lookups`, { query })).data;
}

export async function getRegisterLookup(lookupId: string): Promise<RegisterLookup> {
  return (await api.get<RegisterLookup>(`${TENANT}/register-lookups/${id(lookupId)}`)).data;
}

/** Adds the chosen companies, by LEI, and links the ones the bank already has. */
export async function applyRegisterLookup(lookupId: string, leis: readonly string[]): Promise<RegisterApply> {
  return (await api.post<RegisterApply>(`${TENANT}/register-lookups/${id(lookupId)}/apply`, { leis })).data;
}

/** The library's authorities, for the name of the register each company was looked up in. */
export async function listAuthorities(): Promise<Authority[]> {
  return (await api.get<Authority[]>('/api/v1/authorities')).data;
}
