'use client';

import { NavIcon } from '@/components/shell/NavIcon';
import { useSession } from '@/features/identity/hooks';
import type { Translate } from '@/shared/i18n';

// The bell (design/screens/tenant-notifications.html, blocks 1 and 2; COL-02):
// not a rail row and not a dock item, but an 8px notice-blue dot on the
// account row's icon (and on More below 1024 px) while anything is unread,
// the count as a quiet number at the end of the Notifications row, and the
// count in the accessible name of the row and of More. Everything reads GET
// /me's `counts.unreadNotifications`, which the shell already holds, so there
// is no second request per page; marking read refreshes /me (hooks.ts).

/** How many of the caller's notifications are unread; 0 without a session or counts (a platform session). */
export function useUnreadCount(): number {
  const { me } = useSession();
  return me?.counts?.unreadNotifications ?? 0;
}

/** A label that also says the unread count, "More, 3 unread notifications"; the label alone at 0. */
export function withUnread(label: string, count: number, t: Translate): string {
  return count > 0 ? t('collab.bell.withUnread', { label, unread: t('collab.notifications.unreadCount', { count }) }) : label;
}

const RING = { sidebar: 'ring-sidebar', surface: 'ring-surface' } as const;

/**
 * A navigation icon with the unread dot at its top right, ringed in the fill
 * it sits on so it reads on any row. Hidden from assistive technology: the
 * accessible name says the count.
 */
export function BellIcon({ id, count, size = 'row', ring }: { id: string; count: number; size?: 'row' | 'tab'; ring: keyof typeof RING }) {
  return (
    <span className="relative inline-flex shrink-0">
      <NavIcon id={id} size={size} />
      {count > 0 ? <span aria-hidden="true" data-unread-dot="" className={`absolute -top-0.5 -right-[3px] size-2 rounded-full bg-notice ring-2 ${RING[ring]}`} /> : null}
    </span>
  );
}

/** The quiet number at the end of the Notifications row; nothing at 0. */
export function UnreadCount({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <span aria-hidden="true" data-unread-count="" className="ml-auto text-meta text-muted tabular-nums">
      {count}
    </span>
  );
}
