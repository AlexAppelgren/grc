// The tenant's library-updates feed: what changed in the shared library since
// this reader's bookmark, cut to their footprint (design/screens/tenant-library-updates.html;
// PRO-03, INV-04, FP-03). Every shape is an alias over the generated schemas in
// src/types/api.generated.ts (`bash generate-types.sh`), never redeclared (playbook 6.1).

import type { components, operations } from '@/types/api.generated';

type Schemas = components['schemas'];

export type LibraryUpdatesPage = Schemas['LibraryUpdatesPage'];
export type LibraryUpdateRow = Schemas['LibraryUpdateRow'];
export type LibraryUpdateTarget = Schemas['LibraryUpdateTarget'];

/** The two filters this screen sets, as `GET /library-updates` declares them; paging stays the route's default. */
export type LibraryUpdatesQuery = Pick<NonNullable<operations['listLibraryUpdates']['parameters']['query']>, 'kind' | 'outsideFootprint'>;
