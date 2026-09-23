import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as admin from './api';

// Each wrapper hits its route with its method, body or query and returns `.data`.

describe('tenant-admin api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads and updates the tenant profile', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 't1' } }));
    expect((await admin.getTenant()).id).toBe('t1');
    await admin.updateTenant({ timezone: 'Europe/Helsinki', contentLanguages: ['fi', 'sv', 'en'] });
    expect(sent.map((s) => [s.method, s.path, s.authorization])).toEqual([
      ['get', '/api/v1/tenant', 'Bearer tok'],
      ['patch', '/api/v1/tenant', 'Bearer tok'],
    ]);
    expect(sent[1]?.body).toEqual({ timezone: 'Europe/Helsinki', contentLanguages: ['fi', 'sv', 'en'] });
  });

  it('switches the organisation\'s AI features with a PUT of the one boolean', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 't1', aiEnabled: false } }));
    expect((await admin.setTenantAi(false)).aiEnabled).toBe(false);
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([['put', '/api/v1/tenant/ai', { enabled: false }]]);
  });

  it('lists members with paging and manages one member', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' || s.path.endsWith('reissue-enrolment') ? 204 : 200, data: s.method === 'get' ? { items: [], total: 0 } : { userId: 'u1' } }));
    expect(await admin.listMembers({ limit: 100, offset: 0 })).toEqual({ items: [], total: 0 });
    await admin.inviteMember({ email: 'x@y.z', roleKeys: ['reader'], title: '' });
    await admin.updateMember('u1', { roleKeys: ['reader', 'auditor'] });
    await admin.deactivateMember('u1');
    await admin.reissueEnrolment('u1');
    await admin.listMemberSessions('u1');
    await admin.revokeMemberSessions('u1');
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/tenant/members'],
      ['post', '/api/v1/tenant/members'],
      ['patch', '/api/v1/tenant/members/u1'],
      ['delete', '/api/v1/tenant/members/u1'],
      ['post', '/api/v1/tenant/members/u1/reissue-enrolment'],
      ['get', '/api/v1/tenant/members/u1/sessions'],
      ['delete', '/api/v1/tenant/members/u1/sessions'],
    ]);
    expect(sent[0]?.params).toEqual({ limit: 100, offset: 0 });
    expect(sent[1]?.body).toEqual({ email: 'x@y.z', roleKeys: ['reader'], title: '' });
    expect(sent[2]?.body).toEqual({ roleKeys: ['reader', 'auditor'] });
  });

  it('lists, resends and revokes invitations', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: s.method === 'get' ? { items: [], total: 0 } : { id: 'i1', status: 'pending' } }));
    await admin.listInvitations({ limit: 100, offset: 0 });
    expect((await admin.resendInvitation('i1')).status).toBe('pending');
    await admin.revokeInvitation('i1');
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/tenant/invitations'],
      ['post', '/api/v1/tenant/invitations/i1/resend'],
      ['delete', '/api/v1/tenant/invitations/i1'],
    ]);
  });

  it('lists roles and permissions, creates, updates and retires a role', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'post' && s.path === '/api/v1/tenant/roles' ? 201 : 200, data: s.method === 'get' ? [] : { key: 'legal-reviewer', active: false } }));
    expect(await admin.listRoles()).toEqual([]);
    expect(await admin.listPermissions()).toEqual([]);
    expect(await admin.listLanguages()).toEqual([]);
    await admin.createRole({ key: 'legal-reviewer', labels: { en: 'Legal reviewer', sv: 'Juridisk granskare' }, usageNote: '', permissions: ['cases.read', 'cases.contribute'] });
    await admin.updateRole('legal-reviewer', { labels: { en: 'Legal review' } });
    expect((await admin.retireRole('legal-reviewer')).active).toBe(false);
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/tenant/roles'],
      ['get', '/api/v1/reference/permissions'],
      ['get', '/api/v1/reference/languages'],
      ['post', '/api/v1/tenant/roles'],
      ['patch', '/api/v1/tenant/roles/legal-reviewer'],
      ['post', '/api/v1/tenant/roles/legal-reviewer/retire'],
    ]);
    expect(sent[3]?.body).toMatchObject({ key: 'legal-reviewer', permissions: ['cases.read', 'cases.contribute'] });
  });

  it('lists, creates and revokes API keys and reads the security log', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : s.method === 'post' ? 201 : 200, data: s.method === 'get' ? { items: [], total: 0 } : { id: 'k1', plainKey: 'cw_abc' } }));
    await admin.listApiKeys({ limit: 100, offset: 0 });
    expect((await admin.createApiKey({ name: 'Sync', scopes: ['tenant:read'] })).plainKey).toBe('cw_abc');
    await admin.revokeApiKey('k1');
    expect(await admin.listSecurityLog({ limit: 20, offset: 40 })).toEqual({ items: [], total: 0 });
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/tenant/api-keys'],
      ['post', '/api/v1/tenant/api-keys'],
      ['delete', '/api/v1/tenant/api-keys/k1'],
      ['get', '/api/v1/tenant/security-log'],
    ]);
    expect(sent[3]?.params).toEqual({ limit: 20, offset: 40 });
  });
});
