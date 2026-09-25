'use client';

import Link from 'next/link';

import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { Meta } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

import { formatCollabTime, presentNotification } from './collab-presentation';
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from './hooks';
import { NotificationPreferences } from './NotificationPreferences';
import { useUnreadCount } from './NotificationBell';
import type { Notification } from './types';

// The inbox (design/screens/tenant-notifications.html, blocks 3 to 9; COL-02):
// the caller's own notifications, newest first, 20 a page with Show more.
// A row is the kind's pill, the record's stored title as the link and the
// time in the bank's timezone. Unread rows carry the dot, the heavier title
// and the subtle fill, and a Mark as read button; opening the link marks the
// row read too. Both marks are optimistic and roll back on a failure
// (hooks.ts). A record the reader can no longer open still lists, and its
// link lands on that record's own not-found screen, because the read answers
// 404. The person's own switches sit below the inbox
// (NotificationPreferences.tsx), whatever state the inbox is in.

// Where a notification's record lives, by the subject kind the API names.
// A case is addressed by its change (CHUNK9 ruling 1) but the notification
// carries the case's id, and no screen yet takes one, so a case, like any
// kind without a screen, lists its title without a link.
const RECORD_PATH: Readonly<Record<string, string>> = {
  obligation: '/inventory/obligations/',
  change: '/watch/',
};

export function notificationHref(notification: Pick<Notification, 'subjectType' | 'subjectId'>): string | null {
  const base = Object.hasOwn(RECORD_PATH, notification.subjectType) ? RECORD_PATH[notification.subjectType] : undefined;
  return base === undefined ? null : `${base}${encodeURIComponent(notification.subjectId)}`;
}

function NotificationRow({ notification, now }: { notification: Notification; now: Date }) {
  const t = useT();
  const ctx = useFormatContext();
  const mark = useMarkNotificationRead();
  const unread = notification.readAt === null;
  const href = notificationHref(notification);
  const markRead = () => {
    if (unread) mark.mutate(notification.id);
  };
  return (
    <li
      data-notification-id={notification.id}
      data-unread={unread}
      className={cn('flex flex-wrap items-start gap-x-3 gap-y-2 rounded-card border border-line px-4 py-3', unread ? 'bg-subtle' : 'bg-surface')}
    >
      <span aria-hidden="true" className={cn('mt-1.5 size-2 shrink-0 rounded-full', unread ? 'bg-notice' : 'bg-transparent')} />
      <div className="grid min-w-0 flex-1 gap-1">
        <PillRow pills={presentNotification(notification, t)} />
        <h3 className={unread ? 'font-semibold' : 'font-medium'}>
          {href === null ? (
            notification.title
          ) : (
            <Link href={href} onClick={markRead} className="text-fg underline-offset-3 hover:underline">
              {notification.title}
            </Link>
          )}
        </h3>
        <Meta>
          <span>{formatCollabTime(notification.createdAt, now, ctx, t)}</span>
          {unread ? <span className="sr-only">{t('collab.notifications.unread')}</span> : null}
        </Meta>
        {mark.isError ? (
          <p role="alert" className="m-0 text-meta text-negative">
            {t('collab.notifications.markReadFailed')}
          </p>
        ) : null}
      </div>
      {unread ? (
        <Button variant="ghost" size="small" className="max-sm:ml-5" onClick={markRead}>
          {t('collab.notifications.markRead')}
        </Button>
      ) : null}
    </li>
  );
}

export function NotificationsScreen() {
  const t = useT();
  const inbox = useNotifications();
  const markAll = useMarkAllNotificationsRead();
  const unread = useUnreadCount();
  const rows = inbox.data?.pages.flatMap((page) => page.items) ?? [];
  // One clock per render, so every row counts Today and Yesterday from the same instant.
  const now = new Date();

  return (
    <>
      <PageHead
        title={t('collab.notifications.title')}
        lede={t('collab.notifications.lede')}
        actions={
          <Button variant="outline" size="small" disabled={unread === 0 || markAll.isPending} onClick={() => markAll.mutate()}>
            {t('collab.notifications.markAllRead')}
          </Button>
        }
      />
      {markAll.isError ? <ProblemAlert error={markAll.error} className="mb-3 text-meta text-negative" /> : null}
      {inbox.isPending ? (
        <LoadingState rows={3} />
      ) : inbox.isError ? (
        <ErrorState title={t('collab.notifications.errorTitle')} onRetry={() => void inbox.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title={t('collab.notifications.emptyTitle')} body={t('collab.notifications.emptyBody')} />
      ) : (
        <>
          <ul className="m-0 grid list-none gap-2 p-0" data-notifications-list="">
            {rows.map((notification) => (
              <NotificationRow key={notification.id} notification={notification} now={now} />
            ))}
          </ul>
          {inbox.hasNextPage ? (
            <div className="mt-4 flex justify-center">
              <Button variant="outline" size="small" disabled={inbox.isFetchingNextPage} onClick={() => void inbox.fetchNextPage()}>
                {t('collab.notifications.showMore')}
              </Button>
            </div>
          ) : null}
        </>
      )}
      <NotificationPreferences />
    </>
  );
}
