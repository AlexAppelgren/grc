'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';
import { isAxiosError } from 'axios';

import { homeKeys } from '@/features/home/hooks';
import { CASES_WORK, watchKeys } from '@/features/watch/hooks';
import { hasProblemCode, problemFrom } from '@/shared/utils/problem';

import * as cases from './api';
import type { EvidenceInput } from './api';
import type {
  ActionBody,
  ActionPatch,
  AssessmentBody,
  Case,
  CaseAction,
  CaseActionPage,
  CaseEvidenceCreated,
  CaseEvidencePage,
  CloseBody,
  NoteBody,
  PersonRef,
  ReasonBody,
  TriageBody,
} from './types';

// Query keys and mutations for the case panels on the change page (playbook
// 6.1). The case itself is read with the change (`useChange`), so its
// workflow block, its version and the moves open to this reader always
// arrive together; the lists and the case file are read here.

export const caseKeys = {
  all: ['cases'] as const,
  change: (changeId: string) => ['cases', changeId] as const,
  actions: (changeId: string) => ['cases', changeId, 'actions'] as const,
  evidence: (changeId: string) => ['cases', changeId, 'evidence'] as const,
  caseFile: (changeId: string) => ['cases', changeId, 'case-file'] as const,
};

export function useCaseActions(changeId: string, enabled = true): UseQueryResult<CaseActionPage> {
  return useQuery({ queryKey: caseKeys.actions(changeId), queryFn: () => cases.listActions(changeId), enabled });
}

export function useCaseEvidence(changeId: string, enabled = true): UseQueryResult<CaseEvidencePage> {
  return useQuery({ queryKey: caseKeys.evidence(changeId), queryFn: () => cases.listEvidence(changeId), enabled });
}

export function useCaseFile(changeId: string, enabled = true): UseQueryResult<string> {
  return useQuery({ queryKey: caseKeys.caseFile(changeId), queryFn: () => cases.getCaseFile(changeId), enabled });
}

// ---------------------------------------------------------------------------
// Refused as stale: offer a reload, never merge
// ---------------------------------------------------------------------------

export const STALE_WRITE = 'stale_write';

/**
 * A write somebody else's write overtook: 409 `stale_write`, with the version
 * now current when the server sent it. Nothing was written, and nothing in
 * the cache is touched, so a panel shows the reload offer beside the
 * person's own unsaved input rather than mixing the two.
 */
export function staleWriteOf(error: unknown): { currentVersion: number | null } | null {
  if (!hasProblemCode(error, STALE_WRITE) || !isAxiosError(error)) return null;
  // A `stale_write` code means the answer was a problem body, so the version sits beside it.
  const current = (error.response?.data as { currentVersion?: unknown }).currentVersion;
  return { currentVersion: typeof current === 'number' ? current : null };
}

/**
 * Everything a case write can move: the change page and the feed (its tabs
 * are case categories), the case's own lists and file, and the home screens
 * that count and list cases. Read again, never patched by hand. The reload a
 * stale write offers is the same call.
 */
export function useReloadCase(changeId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: watchKeys.all }),
      queryClient.invalidateQueries({ queryKey: caseKeys.change(changeId) }),
      queryClient.invalidateQueries({ queryKey: homeKeys.home }),
    ]);
  };
}

function useCaseWrite<TData, TVariables>(changeId: string, write: (variables: TVariables) => Promise<TData>): UseMutationResult<TData, unknown, TVariables> {
  const reload = useReloadCase(changeId);
  return useMutation({ mutationFn: write, onSuccess: () => reload() });
}

// ---------------------------------------------------------------------------
// Workflow moves, each carrying the case's version as `If-Match`
// ---------------------------------------------------------------------------

export function useTriageChange(changeId: string, version: number): UseMutationResult<Case, unknown, TriageBody> {
  return useCaseWrite(changeId, (body: TriageBody) => cases.triageChange(changeId, body, version));
}

export function useDismissChange(changeId: string, version: number): UseMutationResult<Case, unknown, ReasonBody> {
  return useCaseWrite(changeId, (body: ReasonBody) => cases.dismissChange(changeId, body, version));
}

export function useRestoreChange(changeId: string, version: number): UseMutationResult<Case, unknown, void> {
  return useCaseWrite(changeId, () => cases.restoreChange(changeId, version));
}

export function useStartAssessment(changeId: string, version: number): UseMutationResult<Case, unknown, void> {
  return useCaseWrite(changeId, () => cases.startAssessment(changeId, version));
}

export function useCloseWithoutAction(changeId: string, version: number): UseMutationResult<Case, unknown, CloseBody> {
  return useCaseWrite(changeId, (body: CloseBody) => cases.closeWithoutAction(changeId, body, version));
}

export function useSaveAssessment(changeId: string, version: number): UseMutationResult<Case, unknown, AssessmentBody> {
  return useCaseWrite(changeId, (body: AssessmentBody) => cases.saveAssessment(changeId, body, version));
}

export function useRequestSignoff(changeId: string, version: number): UseMutationResult<Case, unknown, void> {
  return useCaseWrite(changeId, () => cases.requestSignoff(changeId, version));
}

export function useApproveSignoff(changeId: string, version: number): UseMutationResult<Case, unknown, NoteBody> {
  return useCaseWrite(changeId, (body: NoteBody) => cases.approveSignoff(changeId, body, version));
}

export function useSendBackSignoff(changeId: string, version: number): UseMutationResult<Case, unknown, NoteBody> {
  return useCaseWrite(changeId, (body: NoteBody) => cases.sendBackSignoff(changeId, body, version));
}

// ---------------------------------------------------------------------------
// Actions and evidence
// ---------------------------------------------------------------------------

/** The first action moves the case to implementing, so adding one carries the case's version. */
export function useAddAction(changeId: string, caseVersion: number): UseMutationResult<CaseAction, unknown, ActionBody> {
  return useCaseWrite(changeId, (body: ActionBody) => cases.addAction(changeId, body, caseVersion));
}

/** An edit, a completion or a reopening, carrying the action's own version. */
export function useUpdateAction(changeId: string): UseMutationResult<CaseAction, unknown, { action: Pick<CaseAction, 'id' | 'version'>; patch: ActionPatch }> {
  return useCaseWrite(changeId, ({ action, patch }: { action: Pick<CaseAction, 'id' | 'version'>; patch: ActionPatch }) =>
    cases.updateAction(action.id, patch, action.version),
  );
}

export function useDeleteAction(changeId: string): UseMutationResult<void, unknown, Pick<CaseAction, 'id' | 'version'>> {
  return useCaseWrite(changeId, (action: Pick<CaseAction, 'id' | 'version'>) => cases.deleteAction(action.id, action.version));
}

export function useAddEvidence(changeId: string): UseMutationResult<CaseEvidenceCreated, unknown, EvidenceInput> {
  return useCaseWrite(changeId, (input: EvidenceInput) => cases.addEvidence(changeId, input));
}

export function useRemoveEvidence(changeId: string): UseMutationResult<void, unknown, string> {
  return useCaseWrite(changeId, (evidenceId: string) => cases.removeEvidence(evidenceId));
}

// ---------------------------------------------------------------------------
// c9-fe-triage-assessment: who may own a case
// ---------------------------------------------------------------------------

export const CASES_TRIAGE = 'cases.triage';
export const CASES_CONTRIBUTE = 'cases.contribute';

/** The people a triage may name as owner: active members who hold `cases.work`. */
export function useCaseWorkers(enabled = true): UseQueryResult<PersonRef[]> {
  return useQuery({ queryKey: ['people', CASES_WORK], queryFn: () => cases.listPeople(CASES_WORK), enabled });
}

/**
 * The fields a 422 `validation_error` names in its `errors`, by their last
 * segment (`body.ownerId` is `ownerId`), so a panel shows its own sentence
 * under the field the server refused rather than guessing which one it was.
 */
export function refusedFieldsOf(error: unknown): string[] {
  const problem = problemFrom(error);
  if (problem?.code !== 'validation_error') return [];
  return (problem.errors ?? []).flatMap((item) => {
    const field = typeof item === 'object' && item !== null ? (item as { field?: unknown }).field : undefined;
    return typeof field === 'string' ? [field.split('.').pop() ?? field] : [];
  });
}
