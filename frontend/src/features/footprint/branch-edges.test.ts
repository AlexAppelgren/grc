import { beforeEach, describe, expect, it } from 'vitest';

import { nearMatches } from '@/features/vocabularies/vocabulary-presentation';
import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as footprint from './api';
import { pendingAdditions, toggleTerm } from './footprint-presentation';

// The edges the journeys never reach: a decision that carries a version, a
// proposal answer with fields missing, a draft for a dimension it has not
// seen, and the near-match scores between exact and fuzzy.

const request = { id: 'r1', status: 'rejected', requestedAt: '2026-09-18T12:00:00Z', preview: {} };

describe('footprint edges', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('sends If-Match on a rejection and a withdrawal when the version is known', async () => {
    const sent: string[] = [];
    installAdapter((s) => {
      sent.push(s.path);
      return { status: 200, data: request };
    });
    expect((await footprint.rejectFootprintRequest('r1', { note: 'Ours' }, 4)).status).toBe('rejected');
    expect((await footprint.withdrawFootprintRequest('r1', 5)).status).toBe('rejected');
    expect(sent).toEqual(['/api/v1/tenant/footprint/requests/r1/reject', '/api/v1/tenant/footprint/requests/r1/withdraw']);
  });

  it('reads a proposal answer with its fields missing as empty, never undefined', async () => {
    installAdapter(() => ({ status: 202, data: { proposal: {} } }));
    expect(await footprint.suggestTerm({ dimension: 'channel', labels: { en: 'Robo' } })).toEqual({ id: '', kind: '', status: '', title: '' });
  });

  it('toggles a term in a dimension the draft has not seen, and reads additions of no request as none', () => {
    const draft = toggleTerm({}, 'channel', 'digital');
    expect([...(draft.channel ?? [])]).toEqual(['digital']);
    expect(pendingAdditions(null, 'channel').size).toBe(0);
    expect([...pendingAdditions({ adds: [{ dimension: 'channel', key: 'branch', kind: null, label: 'Branch' }, { dimension: 'regime', key: 'tax', kind: null, label: 'Tax' }] }, 'channel')]).toEqual(['branch']);
  });
});

describe('near matches between exact and fuzzy', () => {
  const rows = [
    { key: 'custody', label: 'Custody', active: true },
    { key: 'custody_services', label: 'Custody services', active: true },
    { key: 'retail_custody', label: 'Retail custody accounts', active: true },
  ];

  it('scores a label that is a prefix of the query, and one that contains it', () => {
    // "custody services x" starts with "Custody" and with "Custody services".
    const longer = nearMatches('custody services x', rows);
    expect(longer.exact).toBeNull();
    expect(longer.matches.map((r) => r.key).slice(0, 2).sort()).toEqual(['custody', 'custody_services']);
    // "accounts" appears inside "Retail custody accounts" only.
    expect(nearMatches('accounts', rows).matches.map((r) => r.key)).toEqual(['retail_custody']);
  });
});
