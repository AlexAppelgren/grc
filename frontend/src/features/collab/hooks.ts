'use client';

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
  type QueryKey,
  type UseInfiniteQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query';

import { identityKeys } from '@/features/identity/hooks';
import type { Me } from '@/features/identity/types';

import * as collab from './api';
import type {
  Comment,
  CommentCreated,
  CommentInput,
  CommentPage,
  CommentPatch,
  CommentSubject,
  MyCommentPage,
  MyCommentsAbout,
  Notification,
  NotificationPage,
  NotificationPrefsPatch,
} from './types';

// Query keys and hooks for the inbox, a record's comments, My work's comments
// and the notification switches (playbook 6.1). The bell's count is GET /me's
// `unreadNotifications`, which the shell already reads, so marking read moves
// that count too and refreshes /me when the server has answered.

export const collabKeys = {
  all: ['collab'] as const,
  notifications: ['collab', 'notifications'] as const,
  inbox: (unread: boolean) => ['collab', 'notifications', { unread }] as const,
  comments: ['collab', 'comments'] as const,
  record: (subject: CommentSubject) => ['collab', 'comments', subject.subjectType, subject.subjectId] as const,
  myComments: ['collab', 'me-comments'] as const,
  mine: (about: MyCommentsAbout) => ['collab', 'me-comments', about] as const,
};

export const COLLAB_PAGE = 20;

function nextOffset<P extends { items: unknown[]; total: number }>(last: P, pages: P[]): number | undefined {
  const read = pages.reduce((sum, page) => sum + page.items.length, 0);
  return read < last.total ? read : undefined;
}

/** The caller's own notifications, newest first, 20 a page; `unread` for only the unread ones. */
export function useNotifications(unread = false): UseInfiniteQueryResult<InfiniteData<NotificationPage>> {
  return useInfiniteQuery({
    queryKey: collabKeys.inbox(unread),
    queryFn: ({ pageParam }) => collab.listNotifications({ unread, limit: COLLAB_PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: nextOffset,
  });
}

interface InboxSnapshot {
  inbox: [QueryKey, InfiniteData<NotificationPage> | undefined][];
  me: Me | null | undefined;
}

/**
 * Marks rows read in every cached inbox page at once, and lowers the bell's
 * count by how many were unread. Returns what it replaced, for the rollback.
 */
async function markReadInCache(queryClient: QueryClient, matches: (n: Notification) => boolean): Promise<InboxSnapshot> {
  await queryClient.cancelQueries({ queryKey: collabKeys.notifications });
  await queryClient.cancelQueries({ queryKey: identityKeys.me, exact: true });
  const snapshot: InboxSnapshot = {
    inbox: queryClient.getQueriesData<InfiniteData<NotificationPage>>({ queryKey: collabKeys.notifications }),
    me: queryClient.getQueryData<Me | null>(identityKeys.me),
  };
  const readAt = new Date().toISOString();
  const marked = new Set<string>();
  queryClient.setQueriesData<InfiniteData<NotificationPage>>({ queryKey: collabKeys.notifications }, (data) =>
    data === undefined
      ? data
      : {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.map((n) => {
              if (n.readAt !== null || !matches(n)) return n;
              marked.add(n.id);
              return { ...n, readAt };
            }),
          })),
        },
  );
  queryClient.setQueryData<Me | null>(identityKeys.me, (me) =>
    me?.counts == null ? me : { ...me, counts: { ...me.counts, unreadNotifications: Math.max(0, me.counts.unreadNotifications - marked.size) } },
  );
  return snapshot;
}

function restore(queryClient: QueryClient, snapshot: InboxSnapshot | undefined): void {
  if (snapshot === undefined) return;
  for (const [key, data] of snapshot.inbox) queryClient.setQueryData(key, data);
  queryClient.setQueryData(identityKeys.me, snapshot.me);
}

function refreshInbox(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: collabKeys.notifications }),
    queryClient.invalidateQueries({ queryKey: identityKeys.me, exact: true }),
  ]);
}

/** Marks one notification read at once on screen; a refused or lost call puts the row and the count back. */
export function useMarkNotificationRead(): UseMutationResult<void, unknown, string, InboxSnapshot> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId) => collab.markNotificationRead(notificationId),
    onMutate: (notificationId) => markReadInCache(queryClient, (n) => n.id === notificationId),
    onError: (_error, _id, snapshot) => restore(queryClient, snapshot),
    onSettled: () => refreshInbox(queryClient),
  });
}

/** "Mark all as read": every cached row and the bell at once, put back if the call fails. */
export function useMarkAllNotificationsRead(): UseMutationResult<void, unknown, void, InboxSnapshot> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => collab.markAllNotificationsRead(),
    onMutate: () => markReadInCache(queryClient, () => true),
    onError: (_error, _vars, snapshot) => restore(queryClient, snapshot),
    onSettled: () => refreshInbox(queryClient),
  });
}

/**
 * One switch saved at once (PATCH /me with that one key). The switch moves
 * on screen before the answer; a refused save puts it back where it was.
 */
export function useUpdateNotificationPrefs(): UseMutationResult<Me, unknown, NotificationPrefsPatch, { me: Me | null | undefined }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch) => collab.updateNotificationPrefs(patch),
    onMutate: async (patch) => {
      await queryClient.cancelQueries({ queryKey: identityKeys.me, exact: true });
      const me = queryClient.getQueryData<Me | null>(identityKeys.me);
      queryClient.setQueryData<Me | null>(identityKeys.me, (current) => {
        if (current?.notificationPrefs == null) return current;
        const changed = Object.fromEntries(Object.entries(patch).filter(([, value]) => typeof value === 'boolean'));
        return { ...current, notificationPrefs: { ...current.notificationPrefs, ...changed } };
      });
      return { me };
    },
    onError: (_error, _patch, snapshot) => {
      if (snapshot !== undefined) queryClient.setQueryData(identityKeys.me, snapshot.me);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: identityKeys.me, exact: true }),
  });
}

/** A record's comments, oldest first, 20 a page; "Show more" loads the newer ones. */
export function useComments(subject: CommentSubject, enabled = true): UseInfiniteQueryResult<InfiniteData<CommentPage>> {
  return useInfiniteQuery({
    queryKey: collabKeys.record(subject),
    queryFn: ({ pageParam }) => collab.listComments({ ...subject, limit: COLLAB_PAGE, offset: pageParam }),
    enabled,
    initialPageParam: 0,
    getNextPageParam: nextOffset,
  });
}

/** My work's panel: the caller's own comments, or the ones that mention them. */
export function useMyComments(about: MyCommentsAbout, enabled = true): UseInfiniteQueryResult<InfiniteData<MyCommentPage>> {
  return useInfiniteQuery({
    queryKey: collabKeys.mine(about),
    queryFn: ({ pageParam }) => collab.listMyComments({ about, limit: COLLAB_PAGE, offset: pageParam }),
    enabled,
    initialPageParam: 0,
    getNextPageParam: nextOffset,
  });
}

// A write changes the record's thread and My work's lists, whether it was
// accepted or refused (a closed edit window, a comment deleted meanwhile).
function refreshComments(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: collabKeys.comments }),
    queryClient.invalidateQueries({ queryKey: collabKeys.myComments }),
  ]);
}

/** Posting a comment. The answer's `undeliveredMentions` is for the author's one-time line. */
export function useAddComment(): UseMutationResult<CommentCreated, unknown, CommentInput> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (body) => collab.addComment(body), onSettled: () => refreshComments(queryClient) });
}

export function useEditComment(): UseMutationResult<Comment, unknown, { commentId: string; body: CommentPatch }> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: ({ commentId, body }) => collab.editComment(commentId, body), onSettled: () => refreshComments(queryClient) });
}

export function useDeleteComment(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (commentId) => collab.deleteComment(commentId), onSettled: () => refreshComments(queryClient) });
}
