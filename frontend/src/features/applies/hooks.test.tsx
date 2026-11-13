import { QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { tokenStore } from '@/shared/utils/api-client';

import { listApplicabilityCompanies } from './api';
import { useApplicabilityCompanies } from './hooks';

// The companies read: one GET on its route, asked only by someone holding register.read.

const COMPANIES = '/api/v1/applicability/companies';
const bank = { orgUnit: { id: 'bank', name: 'Example Bank AB' }, offered: 14, applies: 9, notApplicable: 2, underAssessment: 3 };

function wrapperFor(permissions: readonly string[]) {
  const { queryClient } = queryWrapper();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <PermissionsProvider permissions={permissions}>{children}</PermissionsProvider>
    </QueryClientProvider>
  );
}

describe('applies', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the companies on their route and returns the list', async () => {
    const sent = installAdapter(() => ({ status: 200, data: [bank] }));
    expect(await listApplicabilityCompanies()).toEqual([bank]);
    expect(sent.map((s) => [s.method, s.path])).toEqual([['get', COMPANIES]]);
  });

  it('asks for the companies with register.read', async () => {
    installAdapter(() => ({ status: 200, data: [bank] }));
    const { result } = renderHook(() => useApplicabilityCompanies(), { wrapper: wrapperFor(['register.read']) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([bank]);
  });

  it('never asks without register.read', () => {
    const sent = installAdapter(() => ({ status: 200, data: [bank] }));
    const { result } = renderHook(() => useApplicabilityCompanies(), { wrapper: wrapperFor([]) });
    expect(result.current.fetchStatus).toBe('idle');
    expect(sent).toHaveLength(0);
  });

  it('waits while the session is not known yet', () => {
    const sent = installAdapter(() => ({ status: 200, data: [bank] }));
    const { result } = renderHook(() => useApplicabilityCompanies(), { wrapper: queryWrapper().wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(sent).toHaveLength(0);
  });
});
