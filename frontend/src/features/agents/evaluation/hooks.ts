'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { createEvalQuestion, getEvalBaseline, listAllEvalQuestions, listEvalRuns, type EvalBaseline, type EvalQuestion, type EvalQuestionInput, type EvalRunPage } from './api';

export const evaluationKeys = {
  questions: ['console', 'eval', 'questions'] as const,
  runs: ['console', 'eval', 'runs'] as const,
  baseline: ['console', 'eval', 'baseline'] as const,
};

export function useEvalQuestions(): UseQueryResult<EvalQuestion[]> {
  return useQuery({ queryKey: evaluationKeys.questions, queryFn: listAllEvalQuestions });
}

export function useEvalRuns(): UseQueryResult<EvalRunPage> {
  return useQuery({ queryKey: evaluationKeys.runs, queryFn: listEvalRuns });
}

export function useEvalBaseline(): UseQueryResult<EvalBaseline> {
  return useQuery({ queryKey: evaluationKeys.baseline, queryFn: getEvalBaseline });
}

export function useCreateEvalQuestion(): UseMutationResult<EvalQuestion, unknown, EvalQuestionInput> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: createEvalQuestion, onSuccess: () => queryClient.invalidateQueries({ queryKey: evaluationKeys.questions }) });
}
