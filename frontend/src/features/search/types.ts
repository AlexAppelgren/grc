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
