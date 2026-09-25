import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { AUDIT_LOG_PAGE, governanceKeys, useAuditEvents } from './hooks';

// The read hook keys on the whole query, so a filter change is a new cache
// entry and the previous page stays on screen while it loads.

describe('governance hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads a page of the audit log, and a filtered page under its own key', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: { items: s.params !== null && (s.params as { subjectType?: string }).subjectType === 'api_key' ? [{ id: 'e1' }] : [], total: 1 } }));
    const { wrapper } = queryWrapper();

    const all = renderHook(() => useAuditEvents({ limit: AUDIT_LOG_PAGE, offset: 0 }), { wrapper });
    await waitFor(() => expect(all.result.current.data).toEqual({ items: [], total: 1 }));

    const filtered = renderHook(() => useAuditEvents({ subjectType: 'api_key', limit: AUDIT_LOG_PAGE, offset: 0 }), { wrapper });
    await waitFor(() => expect(filtered.result.current.data).toEqual({ items: [{ id: 'e1' }], total: 1 }));

    expect(sent.map((s) => s.params)).toEqual([
      { limit: 20, offset: 0 },
      { subjectType: 'api_key', limit: 20, offset: 0 },
    ]);
    expect(governanceKeys.auditEvents({ limit: 20, offset: 0 })).toEqual(['audit-events', { limit: 20, offset: 0 }]);
  });
});
