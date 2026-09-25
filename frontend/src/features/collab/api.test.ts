import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as collab from './api';

// The eight collab operations and the switches on PATCH /me: each wrapper's
// method, path, parameters and body, as the contract names them.

describe('collab api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads and marks the inbox', async () => {
    const sent = installAdapter((s) => (s.method === 'get' ? { status: 200, data: { items: [], total: 0 } } : { status: 204 }));
    expect(await collab.listNotifications({ unread: true, limit: 20, offset: 0 })).toEqual({ items: [], total: 0 });
    await collab.markAllNotificationsRead();
    await collab.markNotificationRead('n-1');
    expect(sent.map((s) => [s.method, s.path, s.params, s.authorization])).toEqual([
      ['get', '/api/v1/notifications', { unread: true, limit: 20, offset: 0 }, 'Bearer tok'],
      ['post', '/api/v1/notifications/read-all', null, 'Bearer tok'],
      ['post', '/api/v1/notifications/n-1/read', null, 'Bearer tok'],
    ]);
  });

  it("reads, writes, corrects and deletes a record's comments, and reads My work's", async () => {
    const comment = { id: 'c-1', body: 'Checked.' };
    const sent = installAdapter((s) => {
      if (s.method === 'get') return { status: 200, data: { items: [], total: 0 } };
      if (s.method === 'delete') return { status: 204 };
      return { status: s.method === 'post' ? 201 : 200, data: comment };
    });
    const subject = { subjectType: 'change_case', subjectId: 'case-1' };
    expect(await collab.listComments({ ...subject, limit: 20, offset: 0 })).toEqual({ items: [], total: 0 });
    expect(await collab.addComment({ ...subject, body: 'Checked.', mentionUserIds: ['u-2'] })).toEqual(comment);
    expect(await collab.editComment('c-1', { body: 'Checked twice.' })).toEqual(comment);
    await collab.deleteComment('c-1');
    expect(await collab.listMyComments({ about: 'mentioned', limit: 20, offset: 0 })).toEqual({ items: [], total: 0 });
    expect(sent.map((s) => [s.method, s.path, s.params, s.body])).toEqual([
      ['get', '/api/v1/comments', { ...subject, limit: 20, offset: 0 }, null],
      ['post', '/api/v1/comments', null, { ...subject, body: 'Checked.', mentionUserIds: ['u-2'] }],
      ['patch', '/api/v1/comments/c-1', null, { body: 'Checked twice.' }],
      ['delete', '/api/v1/comments/c-1', null, null],
      ['get', '/api/v1/me/comments', { about: 'mentioned', limit: 20, offset: 0 }, null],
    ]);
  });

  it('sends only the switch that changes, under notificationPrefs', async () => {
    const me = { user: { id: 'u-1' } };
    const sent = installAdapter(() => ({ status: 200, data: me }));
    expect(await collab.updateNotificationPrefs({ mentions: false })).toEqual(me);
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([['patch', '/api/v1/me', { notificationPrefs: { mentions: false } }]]);
  });
});
