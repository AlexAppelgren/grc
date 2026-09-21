import type { PillTone } from '@/components/ui/pill-tones';
import type { CalendarFeed } from '@/features/calendar-feeds/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { Translate } from '@/shared/i18n';

// One pill for the calendar feeds screen (design/screens/tenant-calendar-feeds.html,
// design/system/pills-and-labels.md): whether the subscription still works,
// a fixed status derived from `revokedAt` and never a phrase the API sent.

export type CalendarFeedFacts = Pick<CalendarFeed, 'revokedAt'>;

const STATUS_TONE: Record<'active' | 'revoked', PillTone> = { active: 'positive', revoked: 'information' };

export function presentCalendarFeed(feed: CalendarFeedFacts, t: Translate): PresentedPill[] {
  const revoked = feed.revokedAt !== null;
  return [
    {
      key: revoked ? 'status:revoked' : 'status:active',
      label: revoked ? t('calendarFeeds.revokedPill') : t('calendarFeeds.active'),
      tone: revoked ? STATUS_TONE.revoked : STATUS_TONE.active,
      order: 10,
    },
  ];
}
