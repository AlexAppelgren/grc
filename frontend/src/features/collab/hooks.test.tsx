import { useQuery } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it } from 'vitest';

import { getMe } from '@/features/identity/api';
import { identityKeys } from '@/features/identity/hooks';
import type { Me } from '@/features/identity/types';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import {
  COLLAB_PAGE,
  collabKeys,
  useAddComment,
  useComments,
  useDeleteComment,
  useEditComment,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useMyComments,
  useNotifications,
  useUpdateNotificationPrefs,
} from './hooks';
import type { Notification } from './types';

// Marking read moves the row and the bell at once and puts both back when the
// server refuses; a switch moves at once and goes back on a refused save; a
// comment write refreshes the record's thread and My work.

function notification(id: string, readAt: string | null = null): Notification {
  return { id, kind: 'mention', subjectType: 'change_case', subjectId: 'case-1', title: 'FI adopts amended rules', createdAt: '2026-09-24T08:00:00Z', readAt };
}

const prefs = { weeklyDigest: true, reminders: true, mentions: true, assignments: true, weeklyBriefing: true };
const me = { user: { id: 'u-1' }, counts: { triage: 0, proposals: 0, assignedToMe: 0, unreadNotifications: 2 }, notificationPrefs: prefs } as unknown as Me;

// Holds matching requests until released, so a test can read the cache
// between the optimistic change and the server's answer.
function holdRequests(): { hold: (match: (config: InternalAxiosRequestConfig) => boolean) => () => void } {
  const inner = api.defaults.adapter as AxiosAdapter;
  let held: { match: (config: InternalAxiosRequestConfig) => boolean; gate: Promise<void> } | null = null;
  api.defaults.adapter = async (config) => {
    if (held?.match(config)) await held.gate;
    return inner(config);
  };
  return {
    hold: (match) => {
      let release = () => {};
      held = { match, gate: new Promise<void>((resolve) => (release = resolve)) };
      return release;
    },
  };
}

function server(answers: { markRead?: number; prefs?: number } = {}): (s: Sent) => Answer {
  return (s) => {
    if (s.path === '/api/v1/me' && s.method === 'get') return { status: 200, data: me };
    if (s.path === '/api/v1/me') return { status: answers.prefs ?? 200, data: answers.prefs ? { code: 'unknown_key' } : me };
    if (s.method === 'get') return { status: 200, data: { items: [notification('n-1'), notification('n-2'), notification('n-3', '2026-09-24T09:00:00Z')], total: 3 } };
    return { status: answers.markRead ?? 204 };
  };
}

function useInboxAndMe() {
  return { inbox: useNotifications(), me: useQuery({ queryKey: identityKeys.me, queryFn: getMe }) };
}

const readIds = (result: { current: ReturnType<typeof useInboxAndMe> }) =>
  result.current.inbox.data?.pages.flatMap((p) => p.items).filter((n) => n.readAt !== null).map((n) => n.id);

describe('collab hooks: the inbox', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the inbox a page at a time, and only the unread ones for the bell', async () => {
    const sent = installAdapter((s) => {
      const offset = (s.params as { offset: number }).offset;
      return { status: 200, data: { items: Array.from({ length: offset === 0 ? COLLAB_PAGE : 1 }, (_, i) => notification(`n-${offset + i}`)), total: COLLAB_PAGE + 1 } };
    });
    const { wrapper } = queryWrapper();
    const all = renderHook(() => useNotifications(), { wrapper });
    await waitFor(() => expect(all.result.current.hasNextPage).toBe(true));
    await act(() => all.result.current.fetchNextPage());
    await waitFor(() => expect(all.result.current.hasNextPage).toBe(false));
    const unread = renderHook(() => useNotifications(true), { wrapper });
    await waitFor(() => expect(unread.result.current.isSuccess).toBe(true));
    expect(sent.map((s) => s.params)).toEqual([
      { unread: false, limit: COLLAB_PAGE, offset: 0 },
      { unread: false, limit: COLLAB_PAGE, offset: COLLAB_PAGE },
      { unread: true, limit: COLLAB_PAGE, offset: 0 },
    ]);
    expect(collabKeys.inbox(true)).toEqual(['collab', 'notifications', { unread: true }]);
  });

  it('marks one read at once, lowers the bell by one, and refreshes both when the server answers', async () => {
    const sent = installAdapter(server());
    const { hold } = holdRequests();
    const { wrapper } = queryWrapper();
    const view = renderHook(() => useInboxAndMe(), { wrapper });
    await waitFor(() => expect(view.result.current.me.data).toBeDefined());
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-3']));
    const mark = renderHook(() => useMarkNotificationRead(), { wrapper });

    const release = hold((c) => c.method === 'post');
    act(() => mark.result.current.mutate('n-1'));
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-1', 'n-3']));
    expect(view.result.current.me.data?.counts?.unreadNotifications).toBe(1);

    const gets = sent.filter((s) => s.method === 'get').length;
    release();
    await waitFor(() => expect(mark.result.current.isSuccess).toBe(true));
    expect(sent.filter((s) => s.method === 'post').map((s) => s.path)).toEqual(['/api/v1/notifications/n-1/read']);
    expect(sent.filter((s) => s.method === 'get').length).toBe(gets + 2);
  });

  it('never lowers the bell for a row that was read already', async () => {
    installAdapter(server());
    const { hold } = holdRequests();
    const { wrapper } = queryWrapper();
    const view = renderHook(() => useInboxAndMe(), { wrapper });
    await waitFor(() => expect(view.result.current.me.data).toBeDefined());
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-3']));
    const mark = renderHook(() => useMarkNotificationRead(), { wrapper });
    hold((c) => c.method === 'post');
    act(() => mark.result.current.mutate('n-3'));
    await waitFor(() => expect(mark.result.current.isPending).toBe(true));
    expect(view.result.current.me.data?.counts?.unreadNotifications).toBe(2);
  });

  it('puts the row and the bell back when the server refuses', async () => {
    installAdapter(server({ markRead: 500 }));
    const { hold } = holdRequests();
    const { wrapper } = queryWrapper();
    const view = renderHook(() => useInboxAndMe(), { wrapper });
    await waitFor(() => expect(view.result.current.me.data).toBeDefined());
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-3']));
    const mark = renderHook(() => useMarkNotificationRead(), { wrapper });

    const releasePost = hold((c) => c.method === 'post');
    act(() => mark.result.current.mutate('n-2'));
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-2', 'n-3']));
    expect(view.result.current.me.data?.counts?.unreadNotifications).toBe(1);

    // The refresh after the failure is held, so what the screen shows is the rollback alone.
    const releaseGets = hold((c) => c.method === 'get');
    releasePost();
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-3']));
    expect(view.result.current.me.data?.counts?.unreadNotifications).toBe(2);
    releaseGets();
    await waitFor(() => expect(mark.result.current.isError).toBe(true));
  });

  it('marks every row read at once and empties the bell, and puts them back on a refusal', async () => {
    installAdapter(server({ markRead: 503 }));
    const { hold } = holdRequests();
    const { wrapper } = queryWrapper();
    const view = renderHook(() => useInboxAndMe(), { wrapper });
    await waitFor(() => expect(view.result.current.me.data).toBeDefined());
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-3']));
    const markAll = renderHook(() => useMarkAllNotificationsRead(), { wrapper });

    const releasePost = hold((c) => c.method === 'post');
    act(() => markAll.result.current.mutate());
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-1', 'n-2', 'n-3']));
    expect(view.result.current.me.data?.counts?.unreadNotifications).toBe(0);

    hold((c) => c.method === 'get');
    releasePost();
    await waitFor(() => expect(readIds(view.result)).toEqual(['n-3']));
    expect(view.result.current.me.data?.counts?.unreadNotifications).toBe(2);
  });

  it('marks read while the inbox is still loading, and leaves a session without counts alone', async () => {
    const sent = installAdapter((s) => (s.method === 'get' ? { status: 200, data: { ...me, counts: null } } : { status: 204 }));
    const { hold } = holdRequests();
    const { wrapper, queryClient } = queryWrapper();
    const session = renderHook(() => useQuery({ queryKey: identityKeys.me, queryFn: getMe }), { wrapper });
    await waitFor(() => expect(session.result.current.data).toBeDefined());
    const release = hold((c) => c.method === 'get');
    const inbox = renderHook(() => useNotifications(), { wrapper });
    expect(inbox.result.current.data).toBeUndefined();
    const markAll = renderHook(() => useMarkAllNotificationsRead(), { wrapper });
    act(() => markAll.result.current.mutate());
    await waitFor(() => expect(sent.some((s) => s.method === 'post')).toBe(true));
    release();
    await waitFor(() => expect(markAll.result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData<Me>(identityKeys.me)?.counts).toBeNull();
  });
});

describe('collab hooks: the notification switches', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  function renderSwitches(answers: { prefs?: number }) {
    const sent = installAdapter(server(answers));
    const { hold } = holdRequests();
    const { wrapper } = queryWrapper();
    const session = renderHook(() => useQuery({ queryKey: identityKeys.me, queryFn: getMe }), { wrapper });
    const update = renderHook(() => useUpdateNotificationPrefs(), { wrapper });
    return { sent, hold, session, update };
  }

  it('moves the switch at once, sends only that key, and refreshes the session', async () => {
    const { sent, hold, session, update } = renderSwitches({});
    await waitFor(() => expect(session.result.current.data).toBeDefined());
    const release = hold((c) => c.method === 'patch');
    act(() => update.result.current.mutate({ mentions: false, reminders: null }));
    await waitFor(() => expect(session.result.current.data?.notificationPrefs?.mentions).toBe(false));
    expect(session.result.current.data?.notificationPrefs?.reminders).toBe(true);
    release();
    await waitFor(() => expect(update.result.current.isSuccess).toBe(true));
    expect(sent.filter((s) => s.method === 'patch').map((s) => s.body)).toEqual([{ notificationPrefs: { mentions: false, reminders: null } }]);
    expect(sent.filter((s) => s.method === 'get')).toHaveLength(2);
  });

  it('puts the switch back where it was when the save is refused', async () => {
    const { hold, session, update } = renderSwitches({ prefs: 422 });
    await waitFor(() => expect(session.result.current.data).toBeDefined());
    const releasePatch = hold((c) => c.method === 'patch');
    act(() => update.result.current.mutate({ weeklyDigest: false }));
    await waitFor(() => expect(session.result.current.data?.notificationPrefs?.weeklyDigest).toBe(false));
    hold((c) => c.method === 'get');
    releasePatch();
    await waitFor(() => expect(session.result.current.data?.notificationPrefs?.weeklyDigest).toBe(true));
  });

  it('leaves a session with no bank, and so no switches, as it is', async () => {
    installAdapter((s) => (s.method === 'get' ? { status: 200, data: { ...me, notificationPrefs: null } } : { status: 404, data: { code: 'not_found' } }));
    const { wrapper, queryClient } = queryWrapper();
    const session = renderHook(() => useQuery({ queryKey: identityKeys.me, queryFn: getMe }), { wrapper });
    await waitFor(() => expect(session.result.current.data).toBeDefined());
    const update = renderHook(() => useUpdateNotificationPrefs(), { wrapper });
    act(() => update.result.current.mutate({ mentions: false }));
    await waitFor(() => expect(update.result.current.isError).toBe(true));
    expect(queryClient.getQueryData<Me>(identityKeys.me)?.notificationPrefs).toBeNull();
  });
});

describe('collab hooks: comments', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  const subject = { subjectType: 'change_case', subjectId: 'case-1' };

  it("reads a record's thread and My work's two lists, a page at a time, and nothing while disabled", async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0, permissionLimitedKinds: [] } }));
    const { wrapper } = queryWrapper();
    const off = renderHook(() => useComments(subject, false), { wrapper });
    expect(off.result.current.fetchStatus).toBe('idle');
    const thread = renderHook(() => useComments(subject), { wrapper });
    const mentions = renderHook(() => useMyComments('mentioned'), { wrapper });
    await waitFor(() => expect(thread.result.current.isSuccess && mentions.result.current.isSuccess).toBe(true));
    expect(thread.result.current.hasNextPage).toBe(false);
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/comments', { ...subject, limit: COLLAB_PAGE, offset: 0 }],
      ['/api/v1/me/comments', { about: 'mentioned', limit: COLLAB_PAGE, offset: 0 }],
    ]);
    expect(collabKeys.record(subject)).toEqual(['collab', 'comments', 'change_case', 'case-1']);
    expect(collabKeys.mine('written')).toEqual(['collab', 'me-comments', 'written']);
  });

  it('refreshes the thread and My work after a post, an edit and a delete, and after a refused edit', async () => {
    let patches = 0;
    const sent = installAdapter((s) => {
      if (s.method === 'get') return { status: 200, data: { items: [], total: 0, permissionLimitedKinds: [] } };
      if (s.method === 'post') return { status: 201, data: { id: 'c-1', undeliveredMentions: [{ id: 'u-3', name: 'Johan Berg' }] } };
      if (s.method === 'delete') return { status: 204 };
      patches += 1;
      return patches === 1 ? { status: 200, data: { id: 'c-1' } } : { status: 409, data: { code: 'edit_window_closed' } };
    });
    const { wrapper } = queryWrapper();
    renderHook(() => useComments(subject), { wrapper });
    renderHook(() => useMyComments('written'), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(2));
    const reads = () => sent.filter((s) => s.method === 'get').length;

    const add = renderHook(() => useAddComment(), { wrapper });
    act(() => add.result.current.mutate({ ...subject, body: 'Checked.', mentionUserIds: ['u-3'] }));
    await waitFor(() => expect(add.result.current.isSuccess).toBe(true));
    expect(add.result.current.data?.undeliveredMentions).toEqual([{ id: 'u-3', name: 'Johan Berg' }]);
    expect(reads()).toBe(4);

    const edit = renderHook(() => useEditComment(), { wrapper });
    act(() => edit.result.current.mutate({ commentId: 'c-1', body: { body: 'Checked twice.' } }));
    await waitFor(() => expect(edit.result.current.isSuccess).toBe(true));
    expect(reads()).toBe(6);
    act(() => edit.result.current.mutate({ commentId: 'c-1', body: { body: 'Too late.' } }));
    await waitFor(() => expect(edit.result.current.isError).toBe(true));
    expect(reads()).toBe(8);

    const remove = renderHook(() => useDeleteComment(), { wrapper });
    act(() => remove.result.current.mutate('c-1'));
    await waitFor(() => expect(remove.result.current.isSuccess).toBe(true));
    expect(reads()).toBe(10);
  });
});
