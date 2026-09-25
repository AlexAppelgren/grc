import type { Me } from '@/features/identity/types';
import { api } from '@/shared/utils/api-client';

import type {
  Comment,
  CommentCreated,
  CommentInput,
  CommentPage,
  CommentPatch,
  CommentQuery,
  MyCommentPage,
  MyCommentQuery,
  NotificationPage,
  NotificationPrefsPatch,
  NotificationQuery,
} from './types';

// Thin typed wrappers returning `.data` (playbook 6.1): the eight collab
// operations and the notification switches on PATCH /me. A comment is the
// bank's own text: nothing here logs it.

const NOTIFICATIONS = '/api/v1/notifications';
const COMMENTS = '/api/v1/comments';
const ME = '/api/v1/me';

export async function listNotifications(query: NotificationQuery): Promise<NotificationPage> {
  return (await api.get<NotificationPage>(NOTIFICATIONS, { params: query })).data;
}

export async function markAllNotificationsRead(): Promise<void> {
  await api.post(`${NOTIFICATIONS}/read-all`);
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  await api.post(`${NOTIFICATIONS}/${notificationId}/read`);
}

export async function listComments(query: CommentQuery): Promise<CommentPage> {
  return (await api.get<CommentPage>(COMMENTS, { params: query })).data;
}

export async function addComment(body: CommentInput): Promise<CommentCreated> {
  return (await api.post<CommentCreated>(COMMENTS, body)).data;
}

export async function editComment(commentId: string, body: CommentPatch): Promise<Comment> {
  return (await api.patch<Comment>(`${COMMENTS}/${commentId}`, body)).data;
}

export async function deleteComment(commentId: string): Promise<void> {
  await api.delete(`${COMMENTS}/${commentId}`);
}

export async function listMyComments(query: MyCommentQuery): Promise<MyCommentPage> {
  return (await api.get<MyCommentPage>(`${ME}/comments`, { params: query })).data;
}

/** PATCH /me with only the switches that change; the answer is the whole session. */
export async function updateNotificationPrefs(patch: NotificationPrefsPatch): Promise<Me> {
  return (await api.patch<Me>(ME, { notificationPrefs: patch })).data;
}
