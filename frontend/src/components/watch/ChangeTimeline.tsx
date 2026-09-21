import type { ChangeDetail } from '@/features/watch/api';
import { daysUntil } from '@/features/watch/change-presentation';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { useFormatContext } from '@/features/identity/hooks';
import { cn } from '@/shared/utils/cn';
import { formatPartialDate, type DatePrecision, type FormatContext } from '@/shared/utils/format';

// The timeline of design/screens/tenant-change.html: a reform from
// consultation to in force. Every date is a legal date with a precision, so
// "March 2026", "15 June 2026" and "Q1 2027" are all real answers and the
// screen never prints a day the source did not state (WAT-02).

export type ChangeEvent = ChangeDetail['events'][number];

/**
 * What one entry says beside its label: its date at the precision the source
 * stated, and how long is left when it has not happened yet. `today` is
 * passed in rather than read from the clock, so two entries of one render can
 * never disagree about the days left.
 *
 * A countdown is offered only for a date the source stated to the day: "in
 * 377 days" under a heading that reads "Q4 2027" would be a precision the
 * source never gave.
 */
export function eventMeta(event: ChangeEvent, t: Translate, ctx: FormatContext, today: Date): string[] {
  if (event.eventDate === null) return [t('watch.row.dateNotSet')];
  const meta = [formatPartialDate(event.eventDate, (event.datePrecision ?? 'day') as DatePrecision, ctx)];
  const days = event.occurred || event.datePrecision !== 'day' ? null : daysUntil(event.eventDate, today);
  if (days !== null && days > 0) meta.push(t('watch.row.daysLeft', { count: days }));
  return meta;
}

/** The first entry still ahead, which the card marks as the one being counted down to. */
export function nextEventId(events: readonly ChangeEvent[]): string | null {
  return events.find((event) => !event.occurred)?.id ?? null;
}

export function ChangeTimeline({ events, today }: { events: readonly ChangeEvent[]; today: Date }) {
  const t = useT();
  const ctx = useFormatContext();
  if (events.length === 0) return <p className="text-meta text-muted">{t('watch.change.noTimeline')}</p>;
  const next = nextEventId(events);
  return (
    <ol className="m-0 list-none p-0" data-change-timeline="">
      {events.map((event, index) => (
        <li
          key={event.id}
          data-event-occurred={event.occurred ? '' : undefined}
          className={cn('relative pb-3.5 pl-6 text-meta', event.occurred ? 'text-fg' : 'text-muted', index === events.length - 1 && 'pb-0')}
        >
          <span
            aria-hidden="true"
            className={cn(
              'absolute top-1.5 left-1 h-2.5 w-2.5 rounded-full border-2',
              event.occurred ? 'border-accent bg-accent' : event.id === next ? 'border-brass bg-brass' : 'border-line-control bg-surface',
            )}
          />
          {index < events.length - 1 ? <span aria-hidden="true" className="absolute top-4 bottom-0 left-2 w-px bg-line" /> : null}
          <span className="block font-semibold">{event.label}</span>
          <span className="flex flex-wrap gap-x-2 gap-y-1">
            {eventMeta(event, t, ctx, today).map((line, at) => (
              // Two entries can read the same, so the position is the key.
              <span key={at}>{line}</span>
            ))}
          </span>
        </li>
      ))}
    </ol>
  );
}
