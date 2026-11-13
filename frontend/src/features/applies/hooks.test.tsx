import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { tokenStore } from '@/shared/utils/api-client';

import { listApplicabilityCompanies, listApplicabilityRegulations, listApplicabilityRows, readDecideAll, startDecideAll } from './api';
import { appliesKeys, DECIDE_ALL_POLL_MS, useApplicabilityCompanies, useApplicabilityRegulations, useApplicabilityRows, useDecideAll } from './hooks';

// The What applies reads and Decide all: each on its route, asked only by someone holding
// the permission it needs, the run polled while it works and everything it changed read
// again once it has finished.

const COMPANIES = '/api/v1/applicability/companies';
const REGULATIONS = '/api/v1/applicability/regulations';
const ROWS = '/api/v1/applicability/rows';
const DECIDE_ALL = '/api/v1/applicability/decide-all';
const bank = { orgUnit: { id: 'bank', name: 'Example Bank AB' }, offered: 14, applies: 9, notApplicable: 2, underAssessment: 3, toDecide: 3 };
const page = { items: [], total: 0 };
const idle = { status: 'idle', total: 0, set: 0, skipped: 0, refused: 0, refusals: [], stopped: null, applicability: null, instrument: null, orgUnitId: null, startedAt: null, updatedAt: null };
const running = { ...idle, status: 'running', total: 3, set: 1, applicability: 'applies', orgUnitId: 'bank', startedAt: '2026-11-13T09:00:00Z', updatedAt: '2026-11-13T09:00:01Z' };
const finished = { ...running, status: 'finished', set: 3 };

function wrapperFor(permissions: readonly string[], queryClient: QueryClient = queryWrapper().queryClient) {
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
  afterEach(() => {
    vi.useRealTimers();
  });

  it('reads each list on its route with its query, and starts and reads a run', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'post' ? 202 : 200, data: s.path === COMPANIES ? [bank] : s.path === DECIDE_ALL ? running : page }));
    expect(await listApplicabilityCompanies()).toEqual([bank]);
    expect(await listApplicabilityRegulations({ orgUnitId: 'bank', state: 'to_decide', limit: 20, offset: 0 })).toEqual(page);
    expect(await listApplicabilityRows({ orgUnitId: 'bank', instrument: 'fffs-2017-2', limit: 20, offset: 0 })).toEqual(page);
    expect(await startDecideAll({ orgUnitId: 'bank', applicability: 'applies', reason: 'Licensed.', instrument: 'fffs-2017-2' })).toEqual(running);
    expect(await readDecideAll()).toEqual(running);
    expect(sent.map((s) => [s.method, s.path, s.params, s.body])).toEqual([
      ['get', COMPANIES, null, null],
      ['get', REGULATIONS, { orgUnitId: 'bank', state: 'to_decide', limit: 20, offset: 0 }, null],
      ['get', ROWS, { orgUnitId: 'bank', instrument: 'fffs-2017-2', limit: 20, offset: 0 }, null],
      ['post', DECIDE_ALL, null, { orgUnitId: 'bank', applicability: 'applies', reason: 'Licensed.', instrument: 'fffs-2017-2' }],
      ['get', DECIDE_ALL, null, null],
    ]);
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

  it('keys each list by its query, reads it with register.read, and holds one the screen does not need', async () => {
    const sent = installAdapter(() => ({ status: 200, data: page }));
    const query = { orgUnitId: 'bank', limit: 20, offset: 0 };
    expect(appliesKeys.regulations(query)).toEqual(['applies', 'regulations', query]);
    expect(appliesKeys.rows({ ...query, instrument: 'lvm' })).toEqual(['applies', 'rows', { ...query, instrument: 'lvm' }]);
    const regulations = renderHook(() => useApplicabilityRegulations(query), { wrapper: wrapperFor(['register.read']) });
    const rows = renderHook(() => useApplicabilityRows({ ...query, instrument: 'lvm' }), { wrapper: wrapperFor(['register.read']) });
    await waitFor(() => expect(regulations.result.current.isSuccess && rows.result.current.isSuccess).toBe(true));
    const held = renderHook(() => useApplicabilityRegulations(query, false), { wrapper: wrapperFor(['register.read']) });
    const denied = renderHook(() => useApplicabilityRows({ ...query, instrument: 'lvm' }), { wrapper: wrapperFor([]) });
    expect(held.result.current.fetchStatus).toBe('idle');
    expect(denied.result.current.fetchStatus).toBe('idle');
    expect(sent.map((s) => s.path)).toEqual([REGULATIONS, ROWS]);
  });

  it('reads no run for someone who cannot decide', () => {
    const sent = installAdapter(() => ({ status: 200, data: idle }));
    const { result } = renderHook(() => useDecideAll(false), { wrapper: wrapperFor(['register.read']) });
    expect(result.current.run.fetchStatus).toBe('idle');
    expect(sent).toHaveLength(0);
  });

  it('polls a running run until it finishes, then reads again what it changed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let answer: unknown = running;
    const sent = installAdapter(() => ({ status: 200, data: answer }));
    const { queryClient } = queryWrapper();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useDecideAll(true), { wrapper: wrapperFor(['applicability.approve'], queryClient) });
    await waitFor(() => expect(result.current.run.data).toEqual(running));
    expect(invalidate).not.toHaveBeenCalled();
    answer = finished;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DECIDE_ALL_POLL_MS);
    });
    await waitFor(() => expect(result.current.run.data).toEqual(finished));
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([['applies', 'companies'], ['applies', 'regulations'], ['applies', 'rows'], ['register'], ['library', 'obligations']]);
    const reads = sent.filter((s) => s.path === DECIDE_ALL).length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DECIDE_ALL_POLL_MS * 2);
    });
    expect(sent.filter((s) => s.path === DECIDE_ALL)).toHaveLength(reads);
  });

  it('starts a run and holds the answer as the run read', async () => {
    const sent = installAdapter((s) => (s.method === 'post' ? { status: 202, data: running } : { status: 200, data: idle }));
    const { queryClient } = queryWrapper();
    const { result } = renderHook(() => useDecideAll(true), { wrapper: wrapperFor(['applicability.approve'], queryClient) });
    await waitFor(() => expect(result.current.run.data).toEqual(idle));
    await act(async () => {
      await result.current.start.mutateAsync({ orgUnitId: 'bank', applicability: 'not_applicable', reason: 'No funds.', obligationIds: ['o1'] });
    });
    expect(queryClient.getQueryData(appliesKeys.decideAll)).toEqual(running);
    expect(sent.find((s) => s.method === 'post')?.body).toEqual({ orgUnitId: 'bank', applicability: 'not_applicable', reason: 'No funds.', obligationIds: ['o1'] });
  });
});
