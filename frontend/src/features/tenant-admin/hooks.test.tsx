import { renderHook, waitFor, type RenderHookResult } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import {
  ADMIN_LIST_PAGE,
  adminKeys,
  useApiKeys,
  useCreateApiKey,
  useCreateRole,
  useDeactivateMember,
  useInvitations,
  useInviteMember,
  useLanguages,
  useMembers,
  useMemberSessions,
  usePermissionsReference,
  useReissueEnrolment,
  useResendInvitation,
  useRetireRole,
  useRevokeApiKey,
  useRevokeInvitation,
  useRevokeMemberSessions,
  useRoles,
  useSecurityLog,
  useSetTenantAi,
  useTenant,
  useUpdateMember,
  useUpdateRole,
  useUpdateTenant,
} from './hooks';

// Every hook hits its route and invalidates what the screens read next.

const page = { items: [], total: 0 };

async function settled<T>(rendered: RenderHookResult<{ data: T | undefined }, unknown>): Promise<T> {
  await waitFor(() => expect(rendered.result.current.data).toBeDefined());
  return rendered.result.current.data as T;
}

describe('tenant-admin hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('tenant: switching AI writes the answer into the cache', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 't1', aiEnabled: false } }));
    const { wrapper, queryClient } = queryWrapper();
    const toggle = renderHook(() => useSetTenantAi(), { wrapper });
    await toggle.result.current.mutateAsync(false);
    expect(queryClient.getQueryData(adminKeys.tenant)).toEqual({ id: 't1', aiEnabled: false });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([['put', '/api/v1/tenant/ai', { enabled: false }]]);
  });

  it('tenant: reads, and an update writes the answer into the cache and refreshes me', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.method === 'get' ? { id: 't1', name: 'Old' } : { id: 't1', name: 'New' } }));
    const { wrapper, queryClient } = queryWrapper();
    expect(await settled(renderHook(() => useTenant(), { wrapper }))).toEqual({ id: 't1', name: 'Old' });
    const update = renderHook(() => useUpdateTenant(), { wrapper });
    await update.result.current.mutateAsync({ name: 'New' });
    expect(queryClient.getQueryData(adminKeys.tenant)).toEqual({ id: 't1', name: 'New' });
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/tenant'],
      ['patch', '/api/v1/tenant'],
    ]);
    expect(await settled(renderHook(() => useLanguages(), { wrapper }))).toEqual({ id: 't1', name: 'Old' });
    // Signed out, the list is not asked for at all.
    expect(renderHook(() => useLanguages(false), { wrapper: queryWrapper().wrapper }).result.current.fetchStatus).toBe('idle');
  });

  it('members and invitations: lists at the page maximum, mutations invalidate both lists', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: s.method === 'get' ? page : { userId: 'u1', id: 'i1' } }));
    const { wrapper } = queryWrapper();
    await settled(renderHook(() => useMembers(), { wrapper }));
    await settled(renderHook(() => useInvitations(), { wrapper }));
    expect(sent[0]?.params).toEqual({ limit: ADMIN_LIST_PAGE, offset: 0 });

    await renderHook(() => useInviteMember(), { wrapper }).result.current.mutateAsync({ email: 'x@y.z', roleKeys: ['reader'], title: '' });
    await renderHook(() => useUpdateMember(), { wrapper }).result.current.mutateAsync({ userId: 'u1', body: { title: 'x' } });
    await renderHook(() => useDeactivateMember(), { wrapper }).result.current.mutateAsync('u1');
    await renderHook(() => useReissueEnrolment(), { wrapper }).result.current.mutateAsync('u1');
    await renderHook(() => useRevokeMemberSessions(), { wrapper }).result.current.mutateAsync('u1');
    await renderHook(() => useResendInvitation(), { wrapper }).result.current.mutateAsync('i1');
    await renderHook(() => useRevokeInvitation(), { wrapper }).result.current.mutateAsync('i1');

    await waitFor(() => expect(sent.filter((s) => s.method === 'get' && s.path === '/api/v1/tenant/members').length).toBeGreaterThanOrEqual(2));
    const writes = sent.filter((s) => s.method !== 'get').map((s) => [s.method, s.path]);
    expect(writes).toEqual([
      ['post', '/api/v1/tenant/members'],
      ['patch', '/api/v1/tenant/members/u1'],
      ['delete', '/api/v1/tenant/members/u1'],
      ['post', '/api/v1/tenant/members/u1/reissue-enrolment'],
      ['delete', '/api/v1/tenant/members/u1/sessions'],
      ['post', '/api/v1/tenant/invitations/i1/resend'],
      ['delete', '/api/v1/tenant/invitations/i1'],
    ]);
  });

  it('member sessions: reads one member and does not retry a 404', async () => {
    const sent = installAdapter(() => ({ status: 404, data: { code: 'not_found' } }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useMemberSessions('other'), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(sent).toHaveLength(1);
    expect(sent[0]?.path).toBe('/api/v1/tenant/members/other/sessions');
  });

  it('roles: lists roles and the permission reference, creates, updates and retires', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.method === 'get' ? [] : { key: 'r1' } }));
    const { wrapper } = queryWrapper();
    expect(await settled(renderHook(() => useRoles(), { wrapper }))).toEqual([]);
    expect(await settled(renderHook(() => usePermissionsReference(), { wrapper }))).toEqual([]);
    await renderHook(() => useCreateRole(), { wrapper }).result.current.mutateAsync({ key: 'r1', labels: { en: 'R' }, usageNote: '', permissions: ['cases.read'] });
    await renderHook(() => useUpdateRole(), { wrapper }).result.current.mutateAsync({ key: 'r1', body: { permissions: ['cases.read'] } });
    await renderHook(() => useRetireRole(), { wrapper }).result.current.mutateAsync('r1');
    await waitFor(() => expect(sent.filter((s) => s.method === 'get' && s.path === '/api/v1/tenant/roles').length).toBeGreaterThanOrEqual(2));
    expect(sent.filter((s) => s.method !== 'get').map((s) => [s.method, s.path])).toEqual([
      ['post', '/api/v1/tenant/roles'],
      ['patch', '/api/v1/tenant/roles/r1'],
      ['post', '/api/v1/tenant/roles/r1/retire'],
    ]);
  });

  it('api keys and the security log', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: s.method === 'get' ? { items: [{ id: 1 }], total: 45 } : { id: 'k1', plainKey: 'cw_x' } }));
    const { wrapper } = queryWrapper();
    await settled(renderHook(() => useApiKeys(), { wrapper }));
    const created = await renderHook(() => useCreateApiKey(), { wrapper }).result.current.mutateAsync({ name: 'Sync', scopes: ['tenant:read'] });
    expect(created.plainKey).toBe('cw_x');
    await renderHook(() => useRevokeApiKey(), { wrapper }).result.current.mutateAsync('k1');
    const log = renderHook(({ offset }) => useSecurityLog(offset), { wrapper, initialProps: { offset: 0 } });
    await waitFor(() => expect(log.result.current.data?.total).toBe(45));
    log.rerender({ offset: 20 });
    expect(log.result.current.data?.total).toBe(45);
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/tenant/security-log')).toHaveLength(2));
    expect(sent.filter((s) => s.path === '/api/v1/tenant/security-log').map((s) => s.params)).toEqual([
      { offset: 0, limit: 20 },
      { offset: 20, limit: 20 },
    ]);
    await waitFor(() => expect(sent.filter((s) => s.method === 'get' && s.path === '/api/v1/tenant/api-keys').length).toBeGreaterThanOrEqual(2));
  });
});
