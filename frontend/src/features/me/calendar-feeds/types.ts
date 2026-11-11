// The calendar feeds feature's names for the HOM-04 contract. Every shape is
// an alias over the generated schemas in src/types/api.generated.ts (from the
// backend's OpenAPI export; `bash generate-types.sh` regenerates them).

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

/** One of the caller's own calendar subscriptions. The address is never in this shape (D-52): it is shown once, on creation. */
export type CalendarFeed = Schemas['HomeCalendarFeed'];

/** `POST /calendar-feeds`'s one-time answer: the subscription and the address that carries its secret. */
export type CalendarFeedCreated = Schemas['HomeCalendarFeedCreated'];
