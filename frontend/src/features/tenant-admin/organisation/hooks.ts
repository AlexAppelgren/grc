'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { useDimensions, useTerms } from '@/features/footprint/hooks';
import * as org from '@/features/tenant-admin/organisation/api';
import type {
  Licence,
  LicenceBody,
  LicencePatch,
  OrgUnit,
  OrgUnitBody,
  OrgUnitPatch,
  PersonRef,
  Product,
  ProductBody,
  ProductPatch,
  VersionedPatch,
} from '@/features/tenant-admin/organisation/types';
import { scopeTermGroups, type TermGroup } from '@/features/tenant-admin/organisation/organisation-presentation';
import { usePermissions } from '@/shared/navigation/require-permission';

// Query keys and invalidation for the organisation screen (playbook 6.1). A
// write refetches its own list; a refused write refetches it too, so a
// stale_write leaves the screen on the row as it now stands.

export const orgKeys = {
  units: ['tenant', 'org-units'] as const,
  licences: (unitId: string) => ['tenant', 'org-units', unitId, 'licences'] as const,
  products: ['tenant', 'products'] as const,
  people: ['reference', 'people'] as const,
};

export function useOrgUnits(): UseQueryResult<OrgUnit[]> {
  return useQuery({ queryKey: orgKeys.units, queryFn: org.listOrgUnits });
}

export function useLicences(unitId: string): UseQueryResult<Licence[]> {
  return useQuery({ queryKey: orgKeys.licences(unitId), queryFn: () => org.listLicences(unitId) });
}

export function useProducts(): UseQueryResult<Product[]> {
  return useQuery({ queryKey: orgKeys.products, queryFn: org.listProducts });
}

export function usePeople(): UseQueryResult<PersonRef[]> {
  return useQuery({ queryKey: orgKeys.people, queryFn: org.listPeople, staleTime: 60_000 });
}

function useWrite<V, R>(write: (vars: V) => Promise<R>, key: (vars: V) => readonly unknown[]): UseMutationResult<R, unknown, V> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: write, onSettled: (_data, _error, vars) => queryClient.invalidateQueries({ queryKey: key(vars) }) });
}

export function useCreateOrgUnit(): UseMutationResult<OrgUnit, unknown, OrgUnitBody> {
  return useWrite((body) => org.createOrgUnit(body), () => orgKeys.units);
}

export function useUpdateOrgUnit(): UseMutationResult<OrgUnit, unknown, VersionedPatch<OrgUnitPatch>> {
  return useWrite(({ id, body, version }) => org.updateOrgUnit(id, body, version), () => orgKeys.units);
}

export function useCreateLicence(unitId: string): UseMutationResult<Licence, unknown, LicenceBody> {
  return useWrite((body) => org.createLicence(unitId, body), () => orgKeys.licences(unitId));
}

export function useUpdateLicence(unitId: string): UseMutationResult<Licence, unknown, VersionedPatch<LicencePatch>> {
  return useWrite(({ id, body, version }) => org.updateLicence(id, body, version), () => orgKeys.licences(unitId));
}

export function useCreateProduct(): UseMutationResult<Product, unknown, ProductBody> {
  return useWrite((body) => org.createProduct(body), () => orgKeys.products);
}

export function useUpdateProduct(): UseMutationResult<Product, unknown, VersionedPatch<ProductPatch>> {
  return useWrite(({ id, body, version }) => org.updateProduct(id, body, version), () => orgKeys.products);
}

/** Add and Edit show for vocab.manage; the server checks it again on every write. */
export const useCanEditOrganisation = (): boolean => (usePermissions() ?? []).includes('vocab.manage');

/** The terms an entity, licence or product may carry, grouped by dimension; `only` narrows to one dimension. */
export function useScopeTermGroups(only?: string): TermGroup[] {
  const dimensions = useDimensions();
  const terms = useTerms();
  return scopeTermGroups(dimensions.data ?? [], terms.data ?? [], only);
}
