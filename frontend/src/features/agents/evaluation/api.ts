import { api } from '@/shared/utils/api-client';
import type { components } from '@/types/api.generated';

// The search evaluation set in the platform console (SRC-05, ADM-02): the
// questions the release gate scores search with, the runs recorded against
// them and the baseline the gate holds search to. Every route is gated on
// `eval.manage`; the one write adds a question, which the gate does not score
// until it is written to the gate's file and shipped.

type Schemas = components['schemas'];

export type EvalQuestion = Schemas['EvalQuestionOut'];
export type EvalQuestionInput = Schemas['EvalQuestionInput'];
export type EvalQuestionPage = Schemas['EvalQuestionPage'];
export type EvalRun = Schemas['EvalRunOut'];
export type EvalRunPage = Schemas['EvalRunPage'];
export type EvalBaseline = Schemas['EvalBaselineOut'];
export type EvalScores = Schemas['EvalScores'];

const QUESTIONS = '/api/v1/eval/questions';
const RUNS = '/api/v1/eval/runs';
const BASELINE = '/api/v1/eval/baseline';

/** The route's maximum page. */
export const EVAL_PAGE = 100;
/** The runs shown: the newest page, the rest counted. */
export const EVAL_RUNS_PAGE = 20;

async function questionPage(offset: number): Promise<EvalQuestionPage> {
  return (await api.get<EvalQuestionPage>(QUESTIONS, { params: { limit: EVAL_PAGE, offset } })).data;
}

/**
 * The whole set, every page: the route takes no language filter, and a filter
 * applied to one page would hide questions the server holds. The first page
 * names the total; the rest are asked for at once.
 */
export async function listAllEvalQuestions(): Promise<EvalQuestion[]> {
  const first = await questionPage(0);
  const offsets: number[] = [];
  for (let offset = EVAL_PAGE; offset < first.total; offset += EVAL_PAGE) offsets.push(offset);
  const rest = await Promise.all(offsets.map(questionPage));
  return [first, ...rest].flatMap((page) => page.items);
}

export async function createEvalQuestion(body: EvalQuestionInput): Promise<EvalQuestion> {
  return (await api.post<EvalQuestion>(QUESTIONS, body)).data;
}

export async function listEvalRuns(): Promise<EvalRunPage> {
  return (await api.get<EvalRunPage>(RUNS, { params: { limit: EVAL_RUNS_PAGE, offset: 0 } })).data;
}

export async function getEvalBaseline(): Promise<EvalBaseline> {
  return (await api.get<EvalBaseline>(BASELINE)).data;
}
