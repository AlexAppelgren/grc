import type { CalendarFeed, CalendarFeedCreated } from '@/features/calendar-feeds/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1). Paths are home's
// calendar-feed routes under /api/v1 (HOM-04, D-52, ADR 0045).

const FEEDS = '/api/v1/calendar-feeds';

export async function listCalendarFeeds(): Promise<CalendarFeed[]> {
  return (await api.get<CalendarFeed[]>(FEEDS)).data;
}

// The body carries no fields: every subscription carries the same public
// dates, so there is nothing to choose (D-52). The session must be recent or
// freshly stepped up; the api client's step-up prompt drives off the
// server's own `step_up_required` and retries once.
export async function createCalendarFeed(): Promise<CalendarFeedCreated> {
  return (await api.post<CalendarFeedCreated>(FEEDS, {})).data;
}

export async function revokeCalendarFeed(feedId: string): Promise<void> {
  await api.delete(`${FEEDS}/${encodeURIComponent(feedId)}`);
}
