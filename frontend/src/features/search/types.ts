import type { components, operations } from '@/types/api.generated';

// The wire shapes are the generated ones, never a hand-written copy (playbook
// 6.1): the search contract (`apps/search/schemas.py`) is already camelCase
// and already carries keys rather than labels, so nothing here normalises —
// it only names the pieces the screen reads.

type Schemas = components['schemas'];

/** One ranked result. `matchKind` is on every hit (SRC-02). */
export type SearchHit = Schemas['SearchHit'];
export type SearchResponse = Schemas['SearchResponse'];
export type SearchHitType = Schemas['SearchHitType'];
export type SearchMatchKind = Schemas['SearchMatchKind'];
/** The filters `POST /search` takes: every one of them a key, never a label. */
export type ApiSearchFilters = Schemas['SearchFilters'];

/** The body `POST /search` takes, exactly as the route declares it. */
export type SearchRequestBody = operations['search']['requestBody']['content']['application/json'];

/** The body `POST /ask` takes. The question is the bank's own words: it is sent, never kept. */
export type AskRequestBody = operations['ask']['requestBody']['content']['application/json'];
export type AskStartEvent = Schemas['AskStartEvent'];
export type AskStatementEvent = Schemas['AskStatementEvent'];
export type AskAnswerEvent = Schemas['AskAnswerEvent'];
export type AskProblemEvent = Schemas['AskProblemEvent'];
/** What `POST /ask` streams, one `data:` frame each; `event` names the kind. */
export type AskEvent = AskStartEvent | AskStatementEvent | AskAnswerEvent | AskProblemEvent;
export type Answer = Schemas['Answer'];
export type AnswerStatement = Schemas['AnswerStatement'];
export type AnswerCitation = Schemas['AnswerCitation'];
/** A reader's verdict on one answer, as `POST /answers/{answerId}/feedback` takes it. */
export type AnswerFeedbackBody = Schemas['AnswerFeedbackBody'];
