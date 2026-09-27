import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetApiForTests } from '@/shared/testing/api-adapter';
import { api, pathOf, tokenStore } from '@/shared/utils/api-client';

import * as org from './api';

// Each wrapper hits its route with its method and body, reads the whole list
// in one page at the server's maximum, and sends a change's version as If-Match.

interface Call {
  method: string;
  path: string;
  params: unknown;
  body: unknown;
  ifMatch: unknown;
}

function server(data: unknown): Call[] {
  const calls: Call[] = [];
  const adapter: AxiosAdapter = async (config) => {
    calls.push({
      method: config.method ?? 'get',
      path: pathOf(config),
      params: config.params ?? null,
      body: typeof config.data === 'string' ? JSON.parse(config.data) : null,
      ifMatch: config.headers.get('If-Match') ?? null,
    });
    return { data, status: 200, statusText: '200', headers: {}, config: config as InternalAxiosRequestConfig };
  };
  api.defaults.adapter = adapter;
  return calls;
}

describe('organisation api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the units, one entity licences and the products as lists', async () => {
    const calls = server({ items: [{ id: 'x' }], total: 1 });
    expect(await org.listOrgUnits()).toEqual([{ id: 'x' }]);
    expect(await org.listLicences('u 1')).toEqual([{ id: 'x' }]);
    expect(await org.listProducts()).toEqual([{ id: 'x' }]);
    expect(calls.map((c) => [c.method, c.path, c.params])).toEqual([
      ['get', '/api/v1/tenant/org-units', { limit: 100 }],
      ['get', '/api/v1/tenant/org-units/u%201/licences', { limit: 100 }],
      ['get', '/api/v1/tenant/products', { limit: 100 }],
    ]);
  });

  it('creates without a version and changes with the version it was read at', async () => {
    const calls = server({ id: 'x' });
    await org.createOrgUnit({ kind: 'legal_entity', name: 'Bank AB', orgNumber: '', lei: '', countryCode: '' });
    await org.updateOrgUnit('u1', { name: 'Bank AB' }, 3);
    await org.createLicence('u1', { licenceType: 'bank', reference: '', scopeNote: '', issuer: '', number: '', scopeStatement: '' });
    await org.updateLicence('l1', { withdrawnOn: '2026-12-31' }, 4);
    await org.createProduct({ name: 'Custody', description: '', status: 'live' });
    await org.updateProduct('p1', { status: 'retired' }, 5);
    expect(calls.map((c) => [c.method, c.path, c.ifMatch])).toEqual([
      ['post', '/api/v1/tenant/org-units', null],
      ['patch', '/api/v1/tenant/org-units/u1', '"3"'],
      ['post', '/api/v1/tenant/org-units/u1/licences', null],
      ['patch', '/api/v1/tenant/licences/l1', '"4"'],
      ['post', '/api/v1/tenant/products', null],
      ['patch', '/api/v1/tenant/products/p1', '"5"'],
    ]);
    expect(calls[3]?.body).toEqual({ withdrawnOn: '2026-12-31' });
  });

  it('reads the people picker', async () => {
    const calls = server([{ id: 'u1', name: 'Karin Holm' }]);
    expect(await org.listPeople()).toEqual([{ id: 'u1', name: 'Karin Holm' }]);
    expect(calls[0]?.path).toBe('/api/v1/reference/people');
  });
});
