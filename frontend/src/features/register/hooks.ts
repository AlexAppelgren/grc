'use client';

import { useMutation, useQuery, useQueryClient, type QueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { collabKeys } from '@/features/collab/hooks';
import { participantKeys } from '@/features/participants/hooks';
import { problemReportKeys } from '@/features/problem-reports/hooks';
import { CHANGE_PAGE, watchKeys } from '@/features/watch/hooks';
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
  RegisterEntryWithPanels,
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
  RegisterPanels,
  RegisterPatch,
  RegisterPerson,
  RegisterRiskAcceptanceBody,
  RegisterSpannedEntity,
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
  links: (obligationId: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'links', page] as const,
  units: (obligationId: string, entity: string | undefined, page: RegisterPageQuery) =>
    [...registerKeys.obligation(obligationId), 'units', entity ?? null, page] as const,
  statement: (obligationId: string, entity: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'statement', entity, page] as const,
  duties: (obligationId: string, page: RegisterPageQuery) => [...registerKeys.obligation(obligationId), 'duties', page] as const,
  gapList: (filters: RegisterGapQuery, page: RegisterPageQuery) => ['register', 'gaps', filters, page] as const,
  items: (q: string) => ['register', 'items', q] as const,
};

const spanKey = (obligationId: string) => ['register-span', obligationId] as const;

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

// The obligation page asks once (perf-obligation-page): the register entry carries the first
// page of every panel beside it, and each lands under the key its panel reads, so a panel
// mounted after the entry answered finds its data fresh and sends nothing. A later page, and
// every read after a write, still goes to the panel's own route. The pages here are the ones
// the server fills (backend/apps/register/panels.py).
export const PANEL_PAGE = 20;
export const PANEL_WHOLE_LIST = 100;
export const OBLIGATION_GAPS_PAGE: RegisterPageQuery = { limit: PANEL_WHOLE_LIST };
export const FIRST_ASSESSMENTS_PAGE: RegisterPageQuery = { limit: PANEL_PAGE, offset: 0 };
export const FIRST_UNITS_PAGE: RegisterPageQuery = { limit: PANEL_WHOLE_LIST, offset: 0 };

function seedPanels(queryClient: QueryClient, obligationId: string, panels: RegisterPanels): void {
  // Only where the cache holds nothing yet: data a panel read itself, or re-read after a
  // write, is at least as new and is never replaced.
  const seed = (key: readonly unknown[], data: unknown) => {
    if (queryClient.getQueryData(key) === undefined) queryClient.setQueryData(key, data);
  };
  seed(spanKey(obligationId), panels.spannedEntities);
  seed(registerKeys.gaps(obligationId, OBLIGATION_GAPS_PAGE), panels.gaps);
  seed(registerKeys.assessments(obligationId, FIRST_ASSESSMENTS_PAGE), panels.assessments);
  seed(registerKeys.links(obligationId, {}), panels.internalLinks);
  if (panels.units !== null) seed(registerKeys.units(obligationId, panels.units.orgUnitId, FIRST_UNITS_PAGE), panels.units.units);
  seed(participantKeys.obligation(obligationId), panels.participants);
  // A part the reader's roles may not read comes back null and is left to its own route.
  if (panels.problemReports !== null) seed(problemReportKeys.record('obligation', obligationId), panels.problemReports);
  if (panels.changes !== null) seed(watchKeys.obligationChanges(obligationId, CHANGE_PAGE), panels.changes);
  if (panels.comments !== null) seed(collabKeys.record({ subjectType: 'obligation', subjectId: obligationId }), { pages: [panels.comments], pageParams: [0] });
}

function entryQuery(queryClient: QueryClient, obligationId: string) {
  return {
    queryKey: registerKeys.entry(obligationId),
    queryFn: async () => {
      const entry = await register.getRegisterEntry(obligationId);
      seedPanels(queryClient, obligationId, entry.panels);
      return entry;
    },
  };
}

export function useRegisterEntry(obligationId: string, enabled = true): UseQueryResult<RegisterEntryWithPanels> {
  const queryClient = useQueryClient();
  return useQuery({ ...entryQuery(queryClient, obligationId), enabled });
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
  // Read off the register entry, which carries it, so the page asks once for both.
  const queryClient = useQueryClient();
  return useQuery({ ...entryQuery(queryClient, obligationId), select: (entry) => entry.interpretation });
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

// c8-ui-applicability-status: the entities an answer can be given for, and the people an
// owner or contact picker offers. Neither changes with a register write.

export function useSpannedEntities(obligationId: string): UseQueryResult<RegisterSpannedEntity[]> {
  return useQuery({ queryKey: spanKey(obligationId), queryFn: () => register.listSpannedEntities(obligationId) });
}

export function usePeople(enabled = true): UseQueryResult<RegisterPerson[]> {
  return useQuery({ queryKey: ['reference', 'people'], queryFn: register.listPeople, enabled });
}
