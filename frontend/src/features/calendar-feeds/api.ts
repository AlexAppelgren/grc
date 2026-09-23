import type { CalendarFeed, CalendarFeedCreated } from '@/features/calendar-feeds/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1): home's calendar-feed
// routes under /api/v1 (HOM-04, D-52, ADR 0045). Step-up is the api client's
// business: a 403 step_up_required opens the passkey prompt and retries once.

const FEEDS = '/api/v1/calendar-feeds';

export async function listCalendarFeeds(): Promise<CalendarFeed[]> {
  return (await api.get<CalendarFeed[]>(FEEDS)).data;
}

// The body names no field: every feed carries the same public dates, so
// there is nothing to choose (D-52 removed the "Include" choice).
export async function createCalendarFeed(): Promise<CalendarFeedCreated> {
  return (await api.post<CalendarFeedCreated>(FEEDS, {})).data;
}

export async function revokeCalendarFeed(feedId: string): Promise<void> {
  await api.delete(`${FEEDS}/${encodeURIComponent(feedId)}`);
}
