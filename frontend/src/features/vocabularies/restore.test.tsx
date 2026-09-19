import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as vocab from './api';
import { useRestoreValue, vocabularyKeys } from './hooks';

// Restore is the inverse of retire; on a library list it is a proposal
// like every other write (VOC-07).

const row = { key: 'legacy', kind: null, label: 'Legacy', labels: { en: 'Legacy' }, usageNote: '', sortOrder: 9, active: true, isSystem: false, isDefault: false, usageCount: 2, extra: {} };

describe('restore', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('restores a retired value, or turns a library restore into a proposal', async () => {
    const sent = installAdapter((s) => (s.path.startsWith('/api/v1/vocab/flag') ? { status: 202, data: { proposal: { id: 'p9', kind: 'vocabulary_retire', status: 'open', title: 'Restore AI' } } } : { status: 200, data: row }));
    expect(await vocab.restoreValue('tenant_tag', 'legacy')).toEqual({ outcome: 'applied', result: row });
    expect(await vocab.restoreValue('flag', 'ai')).toEqual({ outcome: 'proposed', proposal: { id: 'p9', kind: 'vocabulary_retire', status: 'open', title: 'Restore AI' } });
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['post', '/api/v1/vocab/tenant_tag/legacy/restore'],
      ['post', '/api/v1/vocab/flag/ai/restore'],
    ]);
  });

  it('restores through the hook and refreshes the list', async () => {
    installAdapter(() => ({ status: 200, data: row }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const restore = renderHook(() => useRestoreValue('tenant_tag'), { wrapper });
    await restore.result.current.mutateAsync('legacy');
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: vocabularyKeys.list('tenant_tag') }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: vocabularyKeys.lists });
  });
});
