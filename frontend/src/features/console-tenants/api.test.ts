import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as consoleTenants from './api';

// The two wrappers hit /console/tenants and return `.data`. Nothing under a
// tenant is ever asked for (ADM-02).

const row = {
  id: 't1',
  name: 'Example Bank AB',
  slug: 'example-bank',
  status: 'active',
  defaultLanguage: { key: 'sv', kind: null, label: 'Swedish' },
  createdAt: '2026-09-19T08:00:00Z',
};

const body = {
  name: 'Third Bank AB',
  slug: 'third-bank',
  timezone: 'Europe/Stockholm',
  defaultLanguage: 'sv',
  contentLanguages: ['sv', 'en'],
  firstAdminEmail: 'administrator@third-bank.test',
  firstAdminTitle: 'Head of compliance',
};

describe('console tenants api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads a page of tenants', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [row], total: 1 } }));
    expect(await consoleTenants.listConsoleTenants({ limit: 100, offset: 0 })).toEqual({ items: [row], total: 1 });
    expect(sent.map((s) => [s.method, s.path, s.params, s.authorization])).toEqual([['get', '/api/v1/console/tenants', { limit: 100, offset: 0 }, 'Bearer tok']]);
  });

  it('creates a tenant with its first administrator', async () => {
    const sent = installAdapter(() => ({ status: 201, data: { ...row, id: 't3', name: body.name, slug: body.slug } }));
    expect(await consoleTenants.createConsoleTenant(body)).toMatchObject({ id: 't3', slug: 'third-bank' });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([['post', '/api/v1/console/tenants', body]]);
  });
});
