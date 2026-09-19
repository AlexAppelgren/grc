import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it } from 'vitest';

import { approveFootprintRequest } from '@/features/footprint/api';
import { createT } from '@/shared/i18n';
import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { exactDuplicateFrom, nearDuplicateFrom, presentListSummary, valueTone } from './vocabulary-presentation';

// The refusal shapes a near duplicate may arrive in, a list the catalog has
// never heard of, and an approval sent before the version is known.

const t = createT('en');

function refusal(data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const response = { data, status: 422, statusText: '422', headers: {}, config } as AxiosResponse;
  return new AxiosError('status 422', '422', config, undefined, response);
}

describe('near-duplicate refusals', () => {
  it('reads the candidates under `errors` as well as `candidates`, dropping malformed ones', () => {
    expect(nearDuplicateFrom(refusal({ code: 'near_duplicate', errors: [{ key: 'custody', label: 'Custody', similarity: 0.8 }, { key: 1 }, null] }))).toEqual([
      { key: 'custody', label: 'Custody', similarity: 0.8 },
    ]);
  });

  it('answers an empty list when the refusal names no candidates, and null for any other error', () => {
    expect(nearDuplicateFrom(refusal({ code: 'near_duplicate', candidates: 'none' }))).toEqual([]);
    expect(nearDuplicateFrom(refusal({ code: 'in_use' }))).toBeNull();
    expect(nearDuplicateFrom(new Error('offline'))).toBeNull();
  });
});

describe('the two refusals of a new value', () => {
  it('tells the same label (409 duplicate_key) from a close one (422 near_duplicate)', () => {
    const exact = refusal({ code: 'duplicate_key', candidates: [{ key: 'custody', label: 'Custody' }] });
    const near = refusal({ code: 'near_duplicate', candidates: [{ key: 'custody', label: 'Custody' }] });
    expect(exactDuplicateFrom(exact)).toEqual([{ key: 'custody', label: 'Custody' }]);
    expect(nearDuplicateFrom(exact)).toBeNull();
    expect(nearDuplicateFrom(near)).toEqual([{ key: 'custody', label: 'Custody' }]);
    expect(exactDuplicateFrom(near)).toBeNull();
  });
});

describe('tone from a kind the scale does not know', () => {
  it('falls back to the neutral tone rather than guessing', () => {
    expect(valueTone('compliance_status', { key: 'x', kind: 'compliant', label: 'Compliant', extra: {} }).tone).toBe('positive');
    expect(valueTone('compliance_status', { key: 'x', kind: 'someday', label: 'Someday', extra: {} }).tone).toBe('information');
    expect(valueTone('risk_rating', { key: 'x', kind: 'high', label: 'High', extra: {} }).tone).toBe('negative');
    expect(valueTone('risk_rating', { key: 'x', kind: 'extreme', label: 'Extreme', extra: {} }).tone).toBe('information');
  });
});

describe('a list the catalog does not know', () => {
  it('reads as its key in plain words, in the neutral tone', () => {
    const [marker] = presentListSummary({ list: 'risk_acceptance_reason', tier: 'tenant', kind: null, count: 2, retiredCount: 0 }, t);
    expect(marker).toMatchObject({ label: 'risk acceptance reason', tone: 'information' });
  });
});

describe('an approval before the version is known', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('is sent without If-Match', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'r1', status: 'approved', requestedAt: '2026-09-18T12:00:00Z', preview: {} } }));
    expect((await approveFootprintRequest('r1')).status).toBe('approved');
    expect(sent[0]?.path).toBe('/api/v1/tenant/footprint/requests/r1/approve');
  });
});
