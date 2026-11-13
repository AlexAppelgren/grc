import type { components, operations } from '@/types/api.generated';
import { api } from '@/shared/utils/api-client';

// "What applies" (REG-01, FP-05): the bank's legal entities, each with how many
// obligations the register offers for it and how its answers stand, one company's
// regulations and their obligations, and Decide all, the run that answers what nobody
// has answered yet. Thin typed wrappers returning `.data` (playbook 6.1;
// backend/apps/register/api.py).

type Schemas = components['schemas'];

/** One legal entity with its offered count and the answers so far. */
export type ApplicabilityCompany = Schemas['RegisterApplicabilityCompany'];
/** One regulation that reaches a company, with its counts and what brings it into scope. */
export type ApplicabilityRegulation = Schemas['RegisterApplicabilityRegulation'];
export type ApplicabilityRegulationPage = Schemas['RegisterApplicabilityRegulationPage'];
/** One obligation of a regulation for a company, with the answer so far. */
export type ApplicabilityAnswer = Schemas['RegisterApplicabilityAnswer'];
export type ApplicabilityAnswerPage = Schemas['RegisterApplicabilityAnswerPage'];
export type RegulationQuery = operations['listApplicabilityRegulations']['parameters']['query'];
export type RowQuery = operations['listApplicabilityRows']['parameters']['query'];
/** The caller's latest Decide all run, as the worker last wrote it. */
export type DecideAll = Schemas['RegisterDecideAll'];
export type DecideAllBody = Schemas['RegisterDecideAllBody'];
/** A reason a model drafted from the licence facts (D-143), labelled as AI until the person sets the answer. */
export type ReasonDraft = Schemas['RegisterReasonDraft'];
export type ReasonDraftBody = Schemas['RegisterReasonDraftBody'];
/** What a draft is for, as the dialog's caller knows it: the company and its filter, without the answer. */
export type ReasonDraftScope = Omit<ReasonDraftBody, 'applicability'>;

const APPLICABILITY = '/api/v1/applicability';

/** Every active legal entity of the bank; a handful, so not paged. */
export async function listApplicabilityCompanies(): Promise<ApplicabilityCompany[]> {
  return (await api.get<ApplicabilityCompany[]>(`${APPLICABILITY}/companies`)).data;
}

export async function listApplicabilityRegulations(query: RegulationQuery): Promise<ApplicabilityRegulationPage> {
  return (await api.get<ApplicabilityRegulationPage>(`${APPLICABILITY}/regulations`, { params: query })).data;
}

export async function listApplicabilityRows(query: RowQuery): Promise<ApplicabilityAnswerPage> {
  return (await api.get<ApplicabilityAnswerPage>(`${APPLICABILITY}/rows`, { params: query })).data;
}

/** Starts a run; the server answers 202 with its state before anything is set. */
export async function startDecideAll(body: DecideAllBody): Promise<DecideAll> {
  return (await api.post<DecideAll>(`${APPLICABILITY}/decide-all`, body)).data;
}

export async function readDecideAll(): Promise<DecideAll> {
  return (await api.get<DecideAll>(`${APPLICABILITY}/decide-all`)).data;
}

/** Asks a model to draft the reason; the server reads the facts itself and stores nothing. */
export async function draftReason(body: ReasonDraftBody): Promise<ReasonDraft> {
  return (await api.post<ReasonDraft>(`${APPLICABILITY}/reason-draft`, body)).data;
}
