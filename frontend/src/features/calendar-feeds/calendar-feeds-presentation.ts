import type { CalendarFeed } from '@/features/calendar-feeds/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { Translate } from '@/shared/i18n';

// The one pill a calendar feed wears (design/screens/tenant-calendar-feeds.html,
// design/system/pills-and-labels.md): whether the address still works. Built
// from `revokedAt`, never a phrase the API sent; tones as `presentApiKey`
// gives a key's status (a revoked credential is a neutral fact).

export type CalendarFeedFacts = Pick<CalendarFeed, 'revokedAt'>;

export function presentCalendarFeed(feed: CalendarFeedFacts, t: Translate): PresentedPill[] {
  return feed.revokedAt === null
    ? [{ key: 'status:active', label: t('calendarFeeds.active'), tone: 'positive', order: 5 }]
    : [{ key: 'status:revoked', label: t('calendarFeeds.revoked'), tone: 'information', order: 5 }];
}
