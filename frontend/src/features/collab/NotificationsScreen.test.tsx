import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AxiosAdapter } from 'axios';
import type { ComponentProps, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import NotificationsPage from '@/app/(tenant)/notifications/page';
import type { Me } from '@/features/identity/types';
import { createT } from '@/shared/i18n';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { api, pathOf, REFRESH_PATH } from '@/shared/utils/api-client';

import { NOTIFICATION_KIND_LABEL } from './collab-presentation';
import { notificationHref, NotificationsScreen } from './NotificationsScreen';
import type { Notification, NotificationKind } from './types';

// The inbox (design/screens/tenant-notifications.html, blocks 3 to 9): every
// kind as its pill, the stored title as the link to its record, unread rows
// marked and markable one at a time or all at once, both at once on screen
// and put back when the server refuses, Show more, and the loading, empty and
// error states.

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: ComponentProps<'a'> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const t = createT('en');
const ME_PATH = '/api/v1/me';
const INBOX_PATH = '/api/v1/notifications';
const READ_ALL_PATH = '/api/v1/notifications/read-all';
const readPath = (id: string) => `/api/v1/notifications/${id}/read`;

function me(unreadNotifications: number): Me {
  return {
    user: { id: 'u1', email: 'sara@example.test', name: 'Sara Lindqvist', locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
    roles: [{ key: 'compliance_officer', kind: null, label: 'Compliance officer' }],
    permissions: ['library.read'],
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 1,
    stepUpValidUntil: null,
    counts: { triage: 0, proposals: 0, assignedToMe: 0, unreadNotifications },
    lastVisitAt: null,
    notificationPrefs: null,
  };
}

function note(id: string, overrides: Partial<Notification> = {}): Notification {
  return {
    id,
    kind: 'mention',
    subjectType: 'obligation',
    subjectId: `ob-${id}`,
    title: `Obligation ${id}`,
    // Now, so the row always reads as today whenever the suite runs.
    createdAt: new Date().toISOString(),
    readAt: null,
    ...overrides,
  };
}

const READ_AT = '2026-09-20T09:00:00Z';

interface Script {
  pages: Notification[][];
  total?: number;
  unread?: number;
  inbox?: Answer;
  markRead?: Answer;
  markAll?: Answer;
}

function server(script: Script): Sent[] {
  const total = script.total ?? script.pages.flat().length;
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: me(script.unread ?? script.pages.flat().filter((n) => n.readAt === null).length) };
    if (sent.path === INBOX_PATH && sent.method === 'get') {
      if (script.inbox !== undefined) return script.inbox;
      const offset = (sent.params as { offset: number }).offset;
      return { status: 200, data: { items: script.pages[offset === 0 ? 0 : 1] ?? [], total } };
    }
    if (sent.path === READ_ALL_PATH) return script.markAll ?? { status: 204 };
    if (sent.method === 'post' && sent.path.endsWith('/read')) return script.markRead ?? { status: 204 };
    return { status: 404, data: { code: 'not_found', detail: 'Not in this test.' } };
  });
}

/** Holds the requests to `path` until released, to read the screen between the optimistic change and the answer. */
function hold(path: string): () => void {
  const inner = api.defaults.adapter as AxiosAdapter;
  let release = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  api.defaults.adapter = async (config) => {
    if (pathOf(config) === path) await gate;
    return inner(config);
  };
  return release;
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const rowOf = (id: string) => document.querySelector(`[data-notification-id="${id}"]`) as HTMLElement;
const posts = (sent: Sent[]) => sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH).map((s) => s.path);
const markAllButton = () => screen.getByRole('button', { name: 'Mark all as read' });

describe('notificationHref', () => {
  it('links an obligation and a change to their screens, and a kind without one to nothing', () => {
    expect(notificationHref({ subjectType: 'obligation', subjectId: 'o-1' })).toBe('/inventory/obligations/o-1');
    expect(notificationHref({ subjectType: 'change', subjectId: 'c-1' })).toBe('/watch/c-1');
    expect(notificationHref({ subjectType: 'change_case', subjectId: 'k-1' })).toBeNull();
    expect(notificationHref({ subjectType: 'toString', subjectId: 'x' })).toBeNull();
  });
});

describe('the notification inbox', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('shows every kind as its pill in the tone its kind decides, and an unknown kind generically', async () => {
    const kinds = Object.keys(NOTIFICATION_KIND_LABEL) as NotificationKind[];
    const rows = kinds.map((kind, i) => note(`n${i}`, { kind }));
    // A kind the API adds before the screen knows it.
    rows.push(note('new', { kind: 'brand_new_kind' as NotificationKind }));
    server({ pages: [rows] });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('n0')).not.toBeNull());
    const tones: Record<string, string> = {};
    kinds.forEach((kind, i) => {
      const pill = rowOf(`n${i}`).querySelector('[data-pill]') as HTMLElement;
      expect(pill).toHaveTextContent(t(NOTIFICATION_KIND_LABEL[kind]));
      tones[kind] = pill.getAttribute('data-pill') ?? '';
    });
    expect(tones).toMatchObject({ mention: 'information', signoff_requested: 'warning', overdue: 'negative', escalation: 'negative', involved_item_changed: 'notice' });
    const generic = rowOf('new').querySelector('[data-pill]') as HTMLElement;
    expect(generic).toHaveTextContent('Notification');
    expect(generic).toHaveAttribute('data-pill', 'information');
  });

  it('lists unread rows with the dot and Mark as read, read rows without, the stored title as the record link', async () => {
    const unread = note('u1');
    const read = note('r1', { readAt: READ_AT, subjectType: 'change', subjectId: 'ch-9', title: 'FI adopts amended rules' });
    const caseRow = note('k1', { subjectType: 'change_case', title: 'A case title', readAt: READ_AT });
    server({ pages: [[unread, read, caseRow]] });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('u1')).not.toBeNull());

    expect(rowOf('u1')).toHaveAttribute('data-unread', 'true');
    expect(within(rowOf('u1')).getByText('Unread')).toBeInTheDocument();
    expect(within(rowOf('u1')).getByRole('button', { name: 'Mark as read' })).toBeInTheDocument();
    expect(within(rowOf('u1')).getByRole('link', { name: 'Obligation u1' })).toHaveAttribute('href', '/inventory/obligations/ob-u1');

    expect(rowOf('r1')).toHaveAttribute('data-unread', 'false');
    expect(within(rowOf('r1')).queryByRole('button')).toBeNull();
    expect(within(rowOf('r1')).queryByText('Unread')).toBeNull();
    // A record the reader may no longer open keeps its link: the record's own screen answers not found.
    expect(within(rowOf('r1')).getByRole('link', { name: 'FI adopts amended rules' })).toHaveAttribute('href', '/watch/ch-9');

    // No screen takes a case's own id yet: its title lists without a link.
    expect(within(rowOf('k1')).getByRole('heading', { name: 'A case title' })).toBeInTheDocument();
    expect(within(rowOf('k1')).queryByRole('link')).toBeNull();
  });

  it('says when each arrived in the bank timezone, today first', async () => {
    server({ pages: [[note('u1')]] });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('u1')).not.toBeNull());
    expect(rowOf('u1')).toHaveTextContent(/Today \d\d:\d\d/);
  });

  it('marks one read at once on screen, then posts it', async () => {
    const sent = server({ pages: [[note('u1'), note('u2')]] });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('u1')).not.toBeNull());
    const release = hold(readPath('u1'));
    fireEvent.click(within(rowOf('u1')).getByRole('button', { name: 'Mark as read' }));
    // Read before the server has answered: the dot, the Unread note and the button go; the row stays in place.
    await waitFor(() => expect(rowOf('u1')).toHaveAttribute('data-unread', 'false'));
    expect(within(rowOf('u1')).queryByRole('button')).toBeNull();
    expect(rowOf('u2')).toHaveAttribute('data-unread', 'true');
    expect(document.querySelectorAll('[data-notification-id]')[0]).toBe(rowOf('u1'));
    release();
    await waitFor(() => expect(posts(sent)).toEqual([readPath('u1')]));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('puts the row back and says so when marking one read fails', async () => {
    server({ pages: [[note('u1')]], markRead: { status: 503, data: { code: 'unavailable', detail: 'Down.' } } });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('u1')).not.toBeNull());
    fireEvent.click(within(rowOf('u1')).getByRole('button', { name: 'Mark as read' }));
    expect(await within(rowOf('u1')).findByRole('alert')).toHaveTextContent('Could not mark it as read. Check your connection and try again.');
    expect(rowOf('u1')).toHaveAttribute('data-unread', 'true');
    expect(within(rowOf('u1')).getByRole('button', { name: 'Mark as read' })).toBeInTheDocument();
  });

  it('marks an unread row read when its link is opened, and a read one sends nothing', async () => {
    const sent = server({ pages: [[note('u1'), note('r1', { readAt: READ_AT })]] });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('u1')).not.toBeNull());
    fireEvent.click(within(rowOf('r1')).getByRole('link'));
    fireEvent.click(within(rowOf('u1')).getByRole('link'));
    await waitFor(() => expect(posts(sent)).toEqual([readPath('u1')]));
  });

  it('marks all read at once, then posts once', async () => {
    const sent = server({ pages: [[note('u1'), note('u2'), note('r1', { readAt: READ_AT })]] });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(markAllButton()).toBeEnabled());
    const release = hold(READ_ALL_PATH);
    fireEvent.click(markAllButton());
    await waitFor(() => expect(document.querySelectorAll('[data-unread="true"]')).toHaveLength(0));
    expect(markAllButton()).toBeDisabled();
    release();
    await waitFor(() => expect(posts(sent)).toEqual([READ_ALL_PATH]));
  });

  it('puts every row back and says why when marking all read fails', async () => {
    server({ pages: [[note('u1'), note('u2')]], markAll: { status: 503, data: { code: 'unavailable', detail: 'The service is unavailable.' } } });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(markAllButton()).toBeEnabled());
    fireEvent.click(markAllButton());
    expect(await screen.findByRole('alert')).toHaveTextContent('The service is unavailable.');
    expect(document.querySelectorAll('[data-unread="true"]')).toHaveLength(2);
    expect(markAllButton()).toBeEnabled();
  });

  it('disables Mark all as read while nothing is unread', async () => {
    server({ pages: [[note('r1', { readAt: READ_AT })]] });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('r1')).not.toBeNull());
    expect(markAllButton()).toBeDisabled();
  });

  it('loads the next 20 with Show more, and offers no more once all are shown', async () => {
    const first = Array.from({ length: 20 }, (_, i) => note(`a${i}`, { readAt: READ_AT }));
    const sent = server({ pages: [first, [note('b0', { readAt: READ_AT })]], total: 21 });
    renderIn(<NotificationsScreen />);
    await waitFor(() => expect(rowOf('a0')).not.toBeNull());
    expect(rowOf('b0')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));
    await waitFor(() => expect(rowOf('b0')).not.toBeNull());
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull();
    const reads = sent.filter((s) => s.path === INBOX_PATH).map((s) => s.params);
    expect(reads).toEqual([
      { unread: false, limit: 20, offset: 0 },
      { unread: false, limit: 20, offset: 20 },
    ]);
  });

  it('shows the loading state until the inbox answers', () => {
    server({ pages: [[note('u1')]] });
    renderIn(<NotificationsScreen />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows the empty state for an empty inbox, never an error', async () => {
    server({ pages: [[]] });
    renderIn(<NotificationsScreen />);
    expect(await screen.findByRole('heading', { name: 'Nothing waiting for you' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(markAllButton()).toBeDisabled();
  });

  it('shows the error state with Try again, which reads the inbox again', async () => {
    let fail = true;
    const sent = installAdapter((s) => {
      if (s.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
      if (s.path === ME_PATH) return { status: 200, data: me(1) };
      if (s.path === INBOX_PATH) return fail ? { status: 500, data: { code: 'server_error', detail: 'Broken.' } } : { status: 200, data: { items: [note('u1')], total: 1 } };
      return { status: 404 };
    });
    renderIn(<NotificationsScreen />);
    expect(await screen.findByRole('heading', { name: 'Could not load your notifications' })).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(rowOf('u1')).not.toBeNull());
    expect(sent.filter((s) => s.path === INBOX_PATH)).toHaveLength(2);
  });

  it('is the /notifications page', async () => {
    server({ pages: [[]] });
    renderIn(<NotificationsPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Notifications' })).toBeInTheDocument();
    await screen.findByRole('heading', { name: 'Nothing waiting for you' });
  });
});
