import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { CONSOLE_TENANTS_PAGE, consoleTenantKeys, useConsoleTenants, useCreateConsoleTenant } from './hooks';
import type { ConsoleTenantCreate } from './types';

// The read hook asks for one page at the server's maximum; creating a tenant
// invalidates that page, so the new bank appears without a reload.

const row = { id: 't1', name: 'Example Bank AB', slug: 'example-bank', status: 'active', defaultLanguage: null, createdAt: '2026-09-19T08:00:00Z' };
const created = { ...row, id: 't3', name: 'Third Bank AB', slug: 'third-bank' };

// Typed, so a field the contract no longer takes fails the typecheck (D-68).
const body: ConsoleTenantCreate = {
  name: 'Third Bank AB',
  firstAdminEmail: 'administrator@third-bank.test',
  firstAdminTitle: '',
};

function server(): Sent[] {
  let tenants = [row];
  return installAdapter((sent: Sent): Answer => {
    if (sent.method === 'post') {
      tenants = [...tenants, created];
      return { status: 201, data: created };
    }
    return { status: 200, data: { items: tenants, total: tenants.length } };
  });
}

describe('console tenants hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads one page at the server maximum, under its own key', async () => {
    const sent = server();
    const { wrapper } = queryWrapper();
    const list = renderHook(() => useConsoleTenants(), { wrapper });
    await waitFor(() => expect(list.result.current.data).toEqual({ items: [row], total: 1 }));
    expect(sent.map((s) => s.params)).toEqual([{ limit: CONSOLE_TENANTS_PAGE, offset: 0 }]);
    expect(consoleTenantKeys.tenants).toEqual(['console', 'tenants']);
  });

  it('shows the new tenant in the list once creating one succeeds', async () => {
    server();
    const { wrapper } = queryWrapper();
    const list = renderHook(() => useConsoleTenants(), { wrapper });
    await waitFor(() => expect(list.result.current.data?.items).toHaveLength(1));

    const create = renderHook(() => useCreateConsoleTenant(), { wrapper });
    create.result.current.mutate(body);
    await waitFor(() => expect(create.result.current.data).toEqual(created));
    await waitFor(() => expect(list.result.current.data?.items.map((t) => t.slug)).toEqual(['example-bank', 'third-bank']));
  });
});
