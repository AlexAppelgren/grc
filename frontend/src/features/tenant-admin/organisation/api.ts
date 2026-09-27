import type { Licence, LicenceBody, LicencePatch, OrgUnit, OrgUnitBody, OrgUnitPatch, PersonRef, Product, ProductBody, ProductPatch } from '@/features/tenant-admin/organisation/types';
import type { Page } from '@/features/tenant-admin/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1) for the organisation
// routes (TEN-02). A change sends the version it was read at as If-Match, so
// a row someone else changed in between is refused with stale_write.

const TENANT = '/api/v1/tenant';
// One page at the server's maximum: a bank's units, one entity's licences and
// its products are short lists.
const ALL = { limit: 100 };

const id = (value: string) => encodeURIComponent(value);

export async function listOrgUnits(): Promise<OrgUnit[]> {
  return (await api.get<Page<OrgUnit>>(`${TENANT}/org-units`, { params: ALL })).data.items;
}

export async function createOrgUnit(body: OrgUnitBody): Promise<OrgUnit> {
  return (await api.post<OrgUnit>(`${TENANT}/org-units`, body)).data;
}

export async function updateOrgUnit(unitId: string, body: OrgUnitPatch, version: number): Promise<OrgUnit> {
  return (await api.patch<OrgUnit>(`${TENANT}/org-units/${id(unitId)}`, body, { version })).data;
}

export async function listLicences(unitId: string): Promise<Licence[]> {
  return (await api.get<Page<Licence>>(`${TENANT}/org-units/${id(unitId)}/licences`, { params: ALL })).data.items;
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
