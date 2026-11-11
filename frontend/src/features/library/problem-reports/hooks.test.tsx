import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { problemReportKeys, RECORD_REPORTS_PAGE, useCloseProblemReport, useRecordProblemReports, useRefreshProblemReports } from './hooks';

// The record's list is keyed by the record; closing a report, and filing one
// elsewhere, refresh every list, a 409 included.

describe('problem report hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it("reads one record's first page, and nothing while disabled", async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const off = renderHook(() => useRecordProblemReports('instrument', 'in-1', false), { wrapper });
    expect(off.result.current.fetchStatus).toBe('idle');
    const on = renderHook(() => useRecordProblemReports('instrument', 'in-1', true), { wrapper });
    await waitFor(() => expect(on.result.current.data).toEqual({ items: [], total: 0 }));
    expect(sent.map((s) => s.params)).toEqual([{ subjectType: 'instrument', subjectId: 'in-1', limit: RECORD_REPORTS_PAGE, offset: 0 }]);
    expect(problemReportKeys.record('instrument', 'in-1')).toEqual(['problem-reports', 'instrument', 'in-1']);
  });

  it('refreshes the list after a close, and after a refused one', async () => {
    let closes = 0;
    const sent = installAdapter((s) => {
      if (s.method === 'get') return { status: 200, data: { items: [], total: 0 } };
      closes += 1;
      return closes === 1 ? { status: 200, data: { id: 'r1', status: 'fixed' } } : { status: 409, data: { code: 'already_closed', detail: 'This report is already closed.' } };
    });
    const { wrapper } = queryWrapper();
    renderHook(() => useRecordProblemReports('obligation', 'ob-1', true), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(1));
    const close = renderHook(() => useCloseProblemReport('r1'), { wrapper });

    act(() => close.result.current.mutate({ status: 'fixed', resolutionNote: 'Corrected.' }));
    await waitFor(() => expect(close.result.current.isSuccess).toBe(true));
    await waitFor(() => expect(sent.filter((s) => s.method === 'get')).toHaveLength(2));

    act(() => close.result.current.mutate({ status: 'fixed', resolutionNote: 'Corrected.' }));
    await waitFor(() => expect(close.result.current.isError).toBe(true));
    await waitFor(() => expect(sent.filter((s) => s.method === 'get')).toHaveLength(3));
  });

  it('refreshes every list for a screen that has just filed a report', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    renderHook(() => useRecordProblemReports('obligation', 'ob-1', true), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(1));
    const refresh = renderHook(() => useRefreshProblemReports(), { wrapper });
    act(() => refresh.result.current());
    await waitFor(() => expect(sent).toHaveLength(2));
  });
});
