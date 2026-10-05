'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { useDimensions, useTerms } from '@/features/footprint/hooks';
import * as org from '@/features/tenant-admin/organisation/api';
import type {
  Authority,
  Licence,
  LicenceBody,
  LicencePatch,
  OrgUnit,
  OrgUnitRow,
  OrgUnitBody,
  OrgUnitPatch,
  PersonRef,
  Product,
  ProductBody,
  ProductPatch,
  RegisterApply,
  RegisterLookup,
  VersionedPatch,
} from '@/features/tenant-admin/organisation/types';
import { scopeTermGroups, type TermGroup } from '@/features/tenant-admin/organisation/organisation-presentation';
import { usePermissions } from '@/shared/navigation/require-permission';

// Query keys and invalidation for the organisation screen (playbook 6.1). A
// write refetches its own list; a refused write refetches it too, so a
// stale_write leaves the screen on the row as it now stands.

export const orgKeys = {
  units: ['tenant', 'org-units'] as const,
  products: ['tenant', 'products'] as const,
  people: ['reference', 'people'] as const,
  lookup: (lookupId: string) => ['tenant', 'register-lookups', lookupId] as const,
  authorities: ['library', 'authorities'] as const,
};

/** How often a running lookup is asked about, as the export job is. */
export const LOOKUP_POLL_MS = 2000;

/** Every unit, each legal entity with its licences: one read for the whole screen. */
export function useOrgUnits(): UseQueryResult<OrgUnitRow[]> {
  return useQuery({ queryKey: orgKeys.units, queryFn: org.listOrgUnits });
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
  return useWrite((body) => org.createLicence(unitId, body), () => orgKeys.units);
}

export function useUpdateLicence(): UseMutationResult<Licence, unknown, VersionedPatch<LicencePatch>> {
  return useWrite(({ id, body, version }) => org.updateLicence(id, body, version), () => orgKeys.units);
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

export function useStartRegisterLookup(): UseMutationResult<RegisterLookup, unknown, string> {
  return useMutation({ mutationFn: (query) => org.startRegisterLookup(query) });
}

/** The lookup's job, asked about until it succeeded or failed; neither changes again. */
export function useRegisterLookup(lookupId: string | null): UseQueryResult<RegisterLookup> {
  return useQuery({
    queryKey: orgKeys.lookup(lookupId ?? ''),
    queryFn: ({ queryKey }) => org.getRegisterLookup(queryKey[2]),
    enabled: lookupId !== null,
    refetchInterval: (query) => (query.state.data?.status === 'succeeded' || query.state.data?.status === 'failed' ? false : LOOKUP_POLL_MS),
  });
}

export function useApplyRegisterLookup(): UseMutationResult<RegisterApply, unknown, { lookupId: string; leis: readonly string[] }> {
  return useWrite(({ lookupId, leis }) => org.applyRegisterLookup(lookupId, leis), () => orgKeys.units);
}

/** The authorities' names, read only by someone who may read the library; the key stands in otherwise. */
export function useAuthorities(): UseQueryResult<Authority[]> {
  const canRead = (usePermissions() ?? []).includes('library.read');
  return useQuery({ queryKey: orgKeys.authorities, queryFn: org.listAuthorities, enabled: canRead, staleTime: 5 * 60_000 });
}
