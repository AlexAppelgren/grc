'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { proposalKeys } from '@/features/proposals/hooks';

import * as vocab from './api';
import type {
  VocabularyCreate,
  VocabularyListSummary,
  VocabularyMergePreview,
  VocabularyRetireResult,
  VocabularyRow,
  VocabularySuggest,
  VocabularySuggestResult,
  VocabularySuggestion,
  VocabularyUpdate,
  VocabularyWrite,
} from './types';

// Query keys and invalidation for the vocabulary screens and every picker
// (playbook 6.1). A list's rows are one query whatever reads them, so a
// value added on the admin screen reaches the pickers on their next render.

export const vocabularyKeys = {
  lists: ['vocab'] as const,
  values: (list: string, includeRetired: boolean) => ['vocab', list, includeRetired ? 'all' : 'active'] as const,
  list: (list: string) => ['vocab', list] as const,
  suggestions: (list: string) => ['vocab', list, 'suggestions'] as const,
};

export function useVocabularies(): UseQueryResult<VocabularyListSummary[]> {
  return useQuery({ queryKey: vocabularyKeys.lists, queryFn: vocab.listVocabularies });
}

export function useVocabularyValues(list: string, includeRetired = false, enabled = true): UseQueryResult<VocabularyRow[]> {
  return useQuery({ queryKey: vocabularyKeys.values(list, includeRetired), queryFn: () => vocab.listValues(list, { includeRetired }), enabled });
}

function useInvalidateList(list: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: vocabularyKeys.list(list) });
    await queryClient.invalidateQueries({ queryKey: vocabularyKeys.lists });
    // A write to a library list is a proposal: what this bank has waiting changes too.
    await queryClient.invalidateQueries({ queryKey: proposalKeys.all });
  };
}

export function useCreateValue(list: string): UseMutationResult<VocabularyWrite<VocabularyRow>, unknown, VocabularyCreate> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: (body) => vocab.createValue(list, body), onSuccess: () => invalidate() });
}

export function useUpdateValue(list: string): UseMutationResult<VocabularyWrite<VocabularyRow>, unknown, { key: string; body: VocabularyUpdate; version?: number }> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: ({ key, body, version }) => vocab.updateValue(list, key, body, version), onSuccess: () => invalidate() });
}

export function useReorderValues(list: string): UseMutationResult<void, unknown, string[]> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: (keys) => vocab.reorderValues(list, keys), onSettled: () => invalidate() });
}

export function useRetireValue(list: string): UseMutationResult<VocabularyWrite<VocabularyRetireResult>, unknown, { key: string; confirm: boolean }> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: ({ key, confirm }) => vocab.retireValue(list, key, confirm), onSuccess: () => invalidate() });
}

export function usePreviewMerge(list: string): UseMutationResult<VocabularyMergePreview, unknown, { key: string; into: string }> {
  return useMutation({ mutationFn: ({ key, into }) => vocab.previewMerge(list, key, into) });
}

export function useMergeValue(list: string): UseMutationResult<VocabularyWrite<VocabularyMergePreview>, unknown, { key: string; into: string }> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: ({ key, into }) => vocab.mergeValue(list, key, into), onSuccess: () => invalidate() });
}

export function useRestoreValue(list: string): UseMutationResult<Awaited<ReturnType<typeof vocab.restoreValue>>, unknown, string> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: (key) => vocab.restoreValue(list, key), onSuccess: () => invalidate() });
}

export function useSuggestValue(list: string): UseMutationResult<VocabularySuggestResult, unknown, VocabularySuggest> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: (body) => vocab.suggestValue(list, body), onSuccess: () => invalidate() });
}

/** The admin's inbox for a tenant list (VOC-03); under the list's key, so any write to the list refreshes it. */
export function useVocabularySuggestions(list: string, enabled = true): UseQueryResult<{ items: VocabularySuggestion[]; total: number }> {
  return useQuery({ queryKey: vocabularyKeys.suggestions(list), queryFn: () => vocab.listSuggestions(list), enabled });
}

export function useDeclineSuggestion(list: string): UseMutationResult<VocabularySuggestion, unknown, string> {
  const invalidate = useInvalidateList(list);
  return useMutation({ mutationFn: (suggestionId) => vocab.declineSuggestion(list, suggestionId), onSuccess: () => invalidate() });
}

