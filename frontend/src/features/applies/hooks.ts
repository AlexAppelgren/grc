'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';
import { useEffect } from 'react';

import { registerKeys } from '@/features/register/hooks';
import { listOrgUnits } from '@/features/tenant-admin/organisation/api';
import { orgKeys } from '@/features/tenant-admin/organisation/hooks';
import { usePermissions } from '@/shared/navigation/require-permission';

import * as applies from './api';
import type { ApplicabilityAnswerPage, ApplicabilityCompany, ApplicabilityRegulationPage, DecideAll, DecideAllBody, RegulationQuery, RowQuery } from './api';
import { basisOf, type Basis, type RegisterRead } from './suggestion';

// Query keys for "What applies" (playbook 6.1). The query is part of each list's key,
// so a new filter or page re-reads rather than filters a stale page.

export const appliesKeys = {
  all: ['applies'] as const,
  companies: ['applies', 'companies'] as const,
  regulations: (query: RegulationQuery) => ['applies', 'regulations', query] as const,
  rows: (query: RowQuery) => ['applies', 'rows', query] as const,
  decideAll: ['applies', 'decide-all'] as const,
};

/** The library's obligation lists, whose rows carry the bank's answer (the inventory, a regulation's page). */
const OBLIGATION_LISTS = ['library', 'obligations'] as const;

function useCanRead(): boolean {
  return (usePermissions() ?? []).includes('register.read');
}

/** The companies and their offered counts, read only by someone holding register.read; nobody else asks. */
export function useApplicabilityCompanies(): UseQueryResult<ApplicabilityCompany[]> {
  const canRead = useCanRead();
  return useQuery({ queryKey: appliesKeys.companies, queryFn: applies.listApplicabilityCompanies, enabled: canRead });
}

/** One company's regulations under a filter, a page at a time. */
export function useApplicabilityRegulations(query: RegulationQuery, enabled = true): UseQueryResult<ApplicabilityRegulationPage> {
  const canRead = useCanRead();
  return useQuery({ queryKey: appliesKeys.regulations(query), queryFn: () => applies.listApplicabilityRegulations(query), enabled: canRead && enabled });
}

/** One regulation's obligations for a company, a page at a time. */
export function useApplicabilityRows(query: RowQuery, enabled = true): UseQueryResult<ApplicabilityAnswerPage> {
  const canRead = useCanRead();
  return useQuery({ queryKey: appliesKeys.rows(query), queryFn: () => applies.listApplicabilityRows(query), enabled: canRead && enabled });
}

/** What a suggested reason for one company's answer to one obligation stands on. */
export interface SuggestionFacts {
  basis: Basis;
  register: RegisterRead | null;
}

/**
 * The facts the obligation page's dialog suggests a reason from, read only while `wanted`
 * (the dialog is open on a company's row nobody has answered) and only by someone holding
 * register.read: the company's regulations matching the regulation's short name, of which
 * the one with this instrument key gives what brings it into scope, and, beside it, the
 * company's register facts. Null while either is read, and when the regulation is not among
 * the company's: then nothing is suggested.
 */
export function useSuggestionFacts(orgUnitId: string, instrument: { key: string; shortName: string } | undefined, wanted: boolean): SuggestionFacts | null {
  const on = useCanRead() && wanted && instrument !== undefined;
  const regulations = useApplicabilityRegulations({ orgUnitId, q: instrument?.shortName }, on);
  const units = useQuery({ queryKey: orgKeys.units, queryFn: listOrgUnits, enabled: on });
  const regulation = regulations.data?.items.find((item) => item.instrument.key === instrument?.key);
  if (regulation === undefined || units.isPending) return null;
  const entry = units.data?.find((unit) => unit.id === orgUnitId)?.registerEntry ?? null;
  return { basis: basisOf(regulation), register: entry === null ? null : { authority: entry.authority.name, readAt: entry.readAt } };
}

/**
 * After one obligation's answer is stored from its own page: what "What applies" and the
 * obligation lists hold about answers is read again. The register's own reads, the
 * regulation page's roll-up among them, the register's write re-reads itself.
 */
export function useRefreshAnswers(): () => void {
  const queryClient = useQueryClient();
  return () => {
    for (const queryKey of [appliesKeys.all, OBLIGATION_LISTS]) void queryClient.invalidateQueries({ queryKey });
  };
}

/** How often the page reads a running Decide all run, in milliseconds. */
export const DECIDE_ALL_POLL_MS = 2000;

/**
 * Decide all, run by the worker, as the library queue's Approve all is (D-128): one call
 * starts it, and the run is read every couple of seconds while it works, so the page shows
 * its progress after a reload too. Once it has finished, the counts, the regulations and
 * the rows are read again, and so is what the regulation page and the obligation page hold
 * about applicability. Only someone holding applicability.approve reads a run.
 */
export function useDecideAll(canApprove: boolean): { run: UseQueryResult<DecideAll>; start: UseMutationResult<DecideAll, unknown, DecideAllBody> } {
  const queryClient = useQueryClient();
  const run = useQuery({
    queryKey: appliesKeys.decideAll,
    queryFn: applies.readDecideAll,
    enabled: canApprove,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? DECIDE_ALL_POLL_MS : false),
  });
  const status = run.data?.status;
  useEffect(() => {
    if (status !== 'finished') return;
    for (const queryKey of [appliesKeys.companies, ['applies', 'regulations'], ['applies', 'rows'], registerKeys.all, OBLIGATION_LISTS]) {
      void queryClient.invalidateQueries({ queryKey });
    }
  }, [status, queryClient]);
  const start = useMutation({
    mutationFn: applies.startDecideAll,
    onSuccess: (started) => queryClient.setQueryData(appliesKeys.decideAll, started),
  });
  return { run, start };
}
