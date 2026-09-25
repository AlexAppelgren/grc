// The collab contract (COL-01, COL-02): the inbox, a record's comments, My
// work's comments and a person's notification switches. Every shape is an
// alias over the generated schemas; nothing is reshaped here.

import type { Page } from '@/features/tenant-admin/types';
import type { components, operations } from '@/types/api.generated';

type Schemas = components['schemas'];

export type { Page };

export type Notification = Schemas['CollabNotification'];
export type NotificationKind = Notification['kind'];
export type NotificationPage = Schemas['CollabNotificationPage'];
export type NotificationQuery = NonNullable<operations['listNotifications']['parameters']['query']>;

export type Comment = Schemas['CollabComment'];
export type PersonRef = Comment['author'];
export type CommentCreated = Schemas['CollabCommentCreated'];
export type CommentInput = Schemas['CollabCommentInput'];
export type CommentPatch = Schemas['CollabCommentPatch'];
export type CommentPage = Schemas['CollabCommentPage'];
export type CommentQuery = operations['listComments']['parameters']['query'];

export type MyComment = Schemas['CollabMyComment'];
export type MyCommentPage = Schemas['CollabMyCommentPage'];
export type MyCommentQuery = operations['listMyComments']['parameters']['query'];
export type MyCommentsAbout = MyCommentQuery['about'];

/** The record a comment belongs to: its kind as a code, and its id. */
export type CommentSubject = Pick<CommentInput, 'subjectType' | 'subjectId'>;

/** A person's notification switches as GET /me returns them, and the ones PATCH /me changes. */
export type NotificationPrefs = Schemas['MembershipNotificationPrefs'];
export type NotificationPrefsPatch = Schemas['MembershipNotificationPrefsPatch'];
