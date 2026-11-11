import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { useObligationTitle } from './hooks';

// A gap names the obligation it sits on by its title, or by its instrument
// when the obligation has no title; nothing until the obligation is read.

const ref = (key: string) => ({ key, kind: null, label: key });

function obligation(id: string, title: { text: string; language: string; isOriginal: boolean; isMachine: boolean } | null) {
  return {
    id,
    stableKey: `obl-${id}`,
    refLabel: '9 kap. 6 §',
    title,
    instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2', officialRef: 'FFFS 2017:2', name: null, implementsNote: '' },
    regime: ref('securities'),
    bindingLevel: ref('authority_regulation'),
    binding: true,
    dutyType: ref('governance'),
    privateToUs: false,
    inFootprint: true,
    summary: null,
    version: null,
    provenance: { sourceUrl: '', sourceLabel: '', lastVerifiedAt: null, verifiedBy: null, createdAt: '2026-09-01T08:00:00Z', createdOrigin: 'user', createdModel: null },
  };
}

describe('useObligationTitle', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('names the obligation by its title, or by its instrument when it has none, and nothing while it loads', async () => {
    const sent = installAdapter((s) => {
      const id = s.path.split('/').pop() ?? '';
      return { status: 200, data: obligation(id, id === 'ob-1' ? { text: 'Pay for research only under the permitted models', language: 'en', isOriginal: true, isMachine: false } : null) };
    });
    const { wrapper } = queryWrapper();
    const titled = renderHook(() => useObligationTitle({ obligationId: 'ob-1' }), { wrapper });
    const untitled = renderHook(() => useObligationTitle({ obligationId: 'ob-2' }), { wrapper });

    expect(titled.result.current).toBeNull();
    await waitFor(() => expect(titled.result.current).toBe('Pay for research only under the permitted models'));
    await waitFor(() => expect(untitled.result.current).toBe('FFFS 2017:2'));
    expect(sent.map((s) => s.path).sort()).toEqual(['/api/v1/obligations/ob-1', '/api/v1/obligations/ob-2']);
  });
});
