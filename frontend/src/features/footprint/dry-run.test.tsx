import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { previewFootprintRequest } from './api';
import { footprintKeys, usePreviewFootprintRequest } from './hooks';

// The dry run: the same request with `dryRun`, answering the preview it would
// store and persisting nothing, so the counted Hides and Reveals appear
// before Request approval.

// As the server sends it (per record kind), and as the screen reads it (per side).
const serverPreview = { obligations: { hidden: 4, revealed: 0, available: true }, cases: { hidden: 0, revealed: 0, available: false } };
const preview = {
  hidden: { obligations: { count: 4, available: true }, cases: { count: 0, available: false } },
  revealed: { obligations: { count: 0, available: true }, cases: { count: 0, available: false } },
};
const body = { adds: [], removes: [{ dimension: 'service_type', key: 'advice' }] };

describe('footprint dry run', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('posts the change with dryRun and reads the preview it would store', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { dryRun: true, removes: [{ dimension: 'service_type', key: 'advice', label: 'Advice' }], preview: serverPreview } }));
    expect(await previewFootprintRequest(body)).toEqual(preview);
    expect(sent.map((s) => [s.method, s.path, s.params, s.body])).toEqual([['post', '/api/v1/tenant/footprint/requests', { dryRun: true }, body]]);
  });

  it('refreshes nothing, because a dry run changed nothing', async () => {
    installAdapter(() => ({ status: 200, data: { dryRun: true, preview: serverPreview } }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const hook = renderHook(() => usePreviewFootprintRequest(), { wrapper });
    await hook.result.current.mutateAsync(body);
    await waitFor(() => expect(hook.result.current.data).toEqual(preview));
    expect(invalidate).not.toHaveBeenCalled();
    expect(footprintKeys.footprint).toEqual(['tenant', 'footprint']);
  });
});
