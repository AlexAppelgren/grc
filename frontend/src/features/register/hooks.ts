'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { hasProblemCode } from '@/shared/utils/problem';

import * as register from './api';
import type {
  RegisterApplicability,
  RegisterApplicabilityBody,
  RegisterApplicabilityMany,
  RegisterApplicabilityManyBody,
  RegisterAssessmentPage,
  RegisterDutyCompleteBody,
  RegisterDutyCompletion,
  RegisterDutyPage,
  RegisterEntityPatch,
  RegisterEntityStatus,
  RegisterEntry,
  RegisterGap,
  RegisterGapBody,
  RegisterGapPage,
  RegisterGapPatch,
  RegisterGapQuery,
  RegisterInternalItemPage,
  RegisterInternalLink,
  RegisterInternalLinkBody,
  RegisterInternalLinkPage,
  RegisterInterpretation,
  RegisterInterpretationBody,
  RegisterPageQuery,
  RegisterPatch,
  RegisterRiskAcceptanceBody,
  RegisterStatementOfApplicability,
  RegisterUnit,
  RegisterUnitBody,
  RegisterUnitPage,
  RegisterUnitPaste,
  RegisterUnitPasteBody,
  RegisterUnitPatch,
} from './types';

// Query keys and invalidation for the register (playbook 6.1). Every panel on
// the obligation page reads through these hooks, so a write in one panel
// reaches the others: status, gaps and history move together. A stale write
// is never retried or merged: the panel keeps what the person typed, says so,
// and offers `useReloadRegister`, which fetches the version someone else saved.

export const STALE_WRITE_CODE = 'stale_write';

export function isStaleWrite(error: unknown): boolean {
  return hasProblemCode(error, STALE_WRITE_CODE);
}

export const registerKeys = {
  all: ['register'] as const,
  obligation: (obligationId: string) => ['register', 'obligation', obligationId] as const,
  entry: (obligationId: string) => [...registerKeys.obligation(obligationId), 'entry'] as const,
  gaps: (obligationId: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'gaps', page] as const,
  assessments: (obligationId: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'assessments', page] as const,
  interpretation: (obligationId: string) => [...registerKeys.obligation(obligationId), 'interpretation'] as const,
  links: (obligationId: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'links', page] as const,
  units: (obligationId: string, entity: string | undefined, page: RegisterPageQuery) =>
    [...registerKeys.obligation(obligationId), 'units', entity ?? null, page] as const,
  statement: (obligationId: string, entity: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'statement', entity, page] as const,
  duties: (obligationId: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'duties', page] as const,
  gapList: (filters: RegisterGapQuery, page: RegisterPageQuery) => ['register', 'gaps', filters, page] as const,
  items: (q: string) => ['register', 'items', q] as const,
};

/** Refetches every register read, which is what a stale write's Reload does. */
export function useReloadRegister(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: registerKeys.all });
}

function useRegisterWrite<T, V>(write: (variables: V) => Promise<T>): UseMutationResult<T, unknown, V> {
  const reload = useReloadRegister();
  return useMutation({ mutationFn: write, onSuccess: () => reload() });
}

// Reads.

export function useRegisterEntry(obligationId: string, enabled = true): UseQueryResult<RegisterEntry> {
  return useQuery({ queryKey: registerKeys.entry(obligationId), queryFn: () => register.getRegisterEntry(obligationId), enabled });
}

export function useObligationGaps(obligationId: string, page: RegisterPageQuery = {}): UseQueryResult<RegisterGapPage> {
  return useQuery({ queryKey: registerKeys.gaps(obligationId, page), queryFn: () => register.listObligationGaps(obligationId, page) });
}

export function useGaps(filters: RegisterGapQuery = {}, page: RegisterPageQuery = {}): UseQueryResult<RegisterGapPage> {
  return useQuery({ queryKey: registerKeys.gapList(filters, page), queryFn: () => register.listGaps(filters, page) });
}

export function useAssessments(obligationId: string, page: RegisterPageQuery = {}): UseQueryResult<RegisterAssessmentPage> {
  return useQuery({ queryKey: registerKeys.assessments(obligationId, page), queryFn: () => register.listAssessments(obligationId, page) });
}

export function useInterpretation(obligationId: string): UseQueryResult<RegisterInterpretation> {
  return useQuery({ queryKey: registerKeys.interpretation(obligationId), queryFn: () => register.getInterpretation(obligationId) });
}

export function useInternalLinks(obligationId: string, page: RegisterPageQuery = {}): UseQueryResult<RegisterInternalLinkPage> {
  return useQuery({ queryKey: registerKeys.links(obligationId, page), queryFn: () => register.listInternalLinks(obligationId, page) });
}

/** The link dialog's search over the bank's own items, read only while the dialog picks. */
export function useInternalItems(q: string, enabled: boolean): UseQueryResult<RegisterInternalItemPage> {
  return useQuery({ queryKey: registerKeys.items(q), queryFn: () => register.listInternalItems(q), enabled });
}

export function useUnits(obligationId: string, entity?: string, page: RegisterPageQuery = {}): UseQueryResult<RegisterUnitPage> {
  return useQuery({ queryKey: registerKeys.units(obligationId, entity, page), queryFn: () => register.listUnits(obligationId, entity, page) });
}

export function useStatementOfApplicability(obligationId: string, entity: string, page: RegisterPageQuery = {}): UseQueryResult<RegisterStatementOfApplicability> {
  return useQuery({
    queryKey: registerKeys.statement(obligationId, entity, page),
    queryFn: () => register.getStatementOfApplicability(obligationId, entity, page),
  });
}

export function useDuties(obligationId: string, page: RegisterPageQuery = {}): UseQueryResult<RegisterDutyPage> {
  return useQuery({ queryKey: registerKeys.duties(obligationId, page), queryFn: () => register.listDuties(obligationId, page) });
}

// Writes. A versioned write takes the `version` the panel last read.

export function useUpdateRegister(obligationId: string): UseMutationResult<RegisterEntry, unknown, { body: RegisterPatch; version: number }> {
  return useRegisterWrite(({ body, version }) => register.updateRegister(obligationId, body, version));
}

export function useUpdateRegisterEntity(
  obligationId: string,
): UseMutationResult<RegisterEntityStatus, unknown, { orgUnitId: string; body: RegisterEntityPatch; version: number }> {
  return useRegisterWrite(({ orgUnitId, body, version }) => register.updateRegisterEntity(obligationId, orgUnitId, body, version));
}

export function useSetApplicability(obligationId: string): UseMutationResult<RegisterApplicability, unknown, { body: RegisterApplicabilityBody; version: number }> {
  return useRegisterWrite(({ body, version }) => register.setApplicability(obligationId, body, version));
}

export function useSetApplicabilityMany(): UseMutationResult<RegisterApplicabilityMany, unknown, RegisterApplicabilityManyBody> {
  return useRegisterWrite(register.setApplicabilityMany);
}

export function useCreateGap(obligationId: string): UseMutationResult<RegisterGap, unknown, RegisterGapBody> {
  return useRegisterWrite((body: RegisterGapBody) => register.createGap(obligationId, body));
}

export function useUpdateGap(): UseMutationResult<RegisterGap, unknown, { gapId: string; body: RegisterGapPatch; version: number }> {
  return useRegisterWrite(({ gapId, body, version }) => register.updateGap(gapId, body, version));
}

export function useRequestRiskAcceptance(): UseMutationResult<RegisterGap, unknown, { gapId: string; body: RegisterRiskAcceptanceBody }> {
  return useRegisterWrite(({ gapId, body }) => register.requestRiskAcceptance(gapId, body));
}

export function useApproveRiskAcceptance(): UseMutationResult<RegisterGap, unknown, string> {
  return useRegisterWrite(register.approveRiskAcceptance);
}

export function useReopenGap(): UseMutationResult<RegisterGap, unknown, string> {
  return useRegisterWrite(register.reopenGap);
}

export function useSaveInterpretation(obligationId: string): UseMutationResult<RegisterInterpretation, unknown, { body: RegisterInterpretationBody; version: number }> {
  return useRegisterWrite(({ body, version }) => register.saveInterpretation(obligationId, body, version));
}

export function useAddInternalLink(obligationId: string): UseMutationResult<RegisterInternalLink, unknown, RegisterInternalLinkBody> {
  return useRegisterWrite((body: RegisterInternalLinkBody) => register.addInternalLink(obligationId, body));
}

export function useRemoveInternalLink(): UseMutationResult<void, unknown, string> {
  return useRegisterWrite(register.removeInternalLink);
}

export function useCreateUnit(obligationId: string): UseMutationResult<RegisterUnit, unknown, RegisterUnitBody> {
  return useRegisterWrite((body: RegisterUnitBody) => register.createUnit(obligationId, body));
}

export function useUpdateUnit(): UseMutationResult<RegisterUnit, unknown, { unitId: string; body: RegisterUnitPatch; version: number }> {
  return useRegisterWrite(({ unitId, body, version }) => register.updateUnit(unitId, body, version));
}

export function useRemoveUnit(): UseMutationResult<void, unknown, { unitId: string; version: number }> {
  return useRegisterWrite(({ unitId, version }) => register.removeUnit(unitId, version));
}

export function usePasteUnits(obligationId: string): UseMutationResult<RegisterUnitPaste, unknown, RegisterUnitPasteBody> {
  return useRegisterWrite((body: RegisterUnitPasteBody) => register.pasteUnits(obligationId, body));
}

export function useCompleteDutyOccurrence(): UseMutationResult<RegisterDutyCompletion, unknown, { occurrenceId: string; body: RegisterDutyCompleteBody }> {
  return useRegisterWrite(({ occurrenceId, body }) => register.completeDutyOccurrence(occurrenceId, body));
}
