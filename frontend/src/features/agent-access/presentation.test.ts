import { describe, expect, it } from 'vitest';

import {
  credentialCounts,
  presentCredential,
  presentEntry,
  presentUnits,
  productsUnder,
  readsNothing,
  scopeTermCount,
  toolName,
} from '@/features/agent-access/presentation';
import type { AccessEntry, AccessKey, OrgUnit, Product } from '@/features/agent-access/types';
import { createT } from '@/shared/i18n';

const t = createT('en');
const NOW = new Date('2026-09-25T10:00:00Z');

const key = (extra: Partial<AccessKey> = {}): AccessKey => ({
  id: 'k1',
  name: 'Order router CI',
  keyPrefix: '7c1e40aa',
  kind: 'service',
  scopes: ['library:read', 'search:read'],
  createdAt: '2026-09-12T08:00:00Z',
  expiresAt: '2026-12-11T08:00:00Z',
  revokedAt: null,
  lastUsedAt: null,
  person: null,
  ...extra,
});

const entry = (extra: Partial<AccessEntry> = {}): AccessEntry => ({
  id: 'e1',
  name: 'Trading platform coding agent',
  purpose: 'Designs and reviews the order-routing service.',
  ownerTeam: { key: 'trading', kind: 'team', label: 'Trading platform team' },
  departments: [],
  products: [],
  tenantReach: true,
  active: true,
  createdBy: { id: 'u1', name: 'Erik Holm' },
  createdAt: '2026-09-12T08:00:00Z',
  revokedAt: null,
  revokedBy: null,
  version: 1,
  keys: [],
  ...extra,
});

const unit = (id: string, parentId: string | null = null, active = true): OrgUnit => ({
  id,
  kind: 'business_area',
  name: id,
  parentId,
  orgNumber: '',
  lei: '',
  countryCode: 'SE',
  entityTerm: null,
  head: null,
  active,
  version: 1,
});

const product = (id: string, orgUnitId: string | null, terms: string[] = ['derivatives'], status: Product['status'] = 'live'): Product => ({
  id,
  name: id,
  description: '',
  status,
  launchDate: null,
  orgUnitId,
  owner: null,
  terms: terms.map((k) => ({ key: k, label: k })),
  version: 1,
});

const labels = (pills: { label: string; tone: string }[]) => pills.map((p) => `${p.label}:${p.tone}`);

describe('agent access presentation', () => {
  it('reads an entry as its state and what it reads now, from both halves of reach', () => {
    expect(labels(presentEntry(entry(), true, t))).toEqual(['Active:positive', 'Reads our register:notice']);
    expect(labels(presentEntry(entry(), false, t))).toEqual(['Active:positive', 'Library only:information']);
    expect(labels(presentEntry(entry({ tenantReach: false }), true, t))).toEqual(['Active:positive', 'Library only:information']);
  });

  it('draws no reach pill while the organisation switch is unknown, and none on a revoked entry', () => {
    expect(labels(presentEntry(entry(), null, t))).toEqual(['Active:positive']);
    expect(labels(presentEntry(entry({ active: false }), true, t))).toEqual(['Revoked:information']);
  });

  it('draws departments and products as brand pills, the scope facets', () => {
    expect(labels(presentUnits([{ id: 'd1', name: 'Trading' }], 'department'))).toEqual(['Trading:brand']);
  });

  it('reads a credential as its kind, then Revoked or Expired from its facts, then its scopes', () => {
    expect(labels(presentCredential(key(), t, NOW))).toEqual(['Service:information', 'library read:information', 'search read:information']);
    expect(labels(presentCredential(key({ kind: 'personal', scopes: [] }), t, NOW))).toEqual(['Personal:information']);
    expect(labels(presentCredential(key({ scopes: [], expiresAt: '2026-09-18T00:00:00Z' }), t, NOW))).toEqual(['Service:information', 'Expired:warning']);
    expect(labels(presentCredential(key({ scopes: [], expiresAt: '2026-09-18T00:00:00Z', revokedAt: '2026-09-17T00:00:00Z' }), t, NOW))).toEqual(['Service:information', 'Revoked:information']);
  });

  it('counts the service keys and personal tokens under an entry and their latest use', () => {
    const counts = credentialCounts([key({ lastUsedAt: '2026-09-20T00:00:00Z' }), key({ id: 'k2', lastUsedAt: '2026-09-25T08:41:00Z' }), key({ id: 't1', kind: 'personal' })]);
    expect(counts).toEqual({ keys: 2, tokens: 1, lastUsedAt: '2026-09-25T08:41:00Z' });
    expect(credentialCounts([])).toEqual({ keys: 0, tokens: 0, lastUsedAt: null });
  });

  it('finds the live products a department brings, its own and those of every active unit below it', () => {
    const units = [unit('trading'), unit('desk', 'trading'), unit('closed', 'trading', false), unit('cards')];
    const products = [product('derivatives', 'trading'), product('routing', 'desk'), product('old', 'closed'), product('gone', 'desk', ['x'], 'retired'), product('card', 'cards')];
    expect(productsUnder('trading', units, products).map((p) => p.id)).toEqual(['derivatives', 'routing']);
    expect(productsUnder('cards', units, products).map((p) => p.id)).toEqual(['card']);
  });

  it('warns only when what was named derives no term at all', () => {
    const units = [unit('trading'), unit('procurement')];
    const products = [product('derivatives', 'trading'), product('termless', null, [])];
    expect(readsNothing({ departmentIds: [], productIds: [] }, units, products)).toBe(false);
    expect(readsNothing({ departmentIds: ['procurement'], productIds: [] }, units, products)).toBe(true);
    expect(readsNothing({ departmentIds: ['procurement'], productIds: ['derivatives'] }, units, products)).toBe(false);
    expect(readsNothing({ departmentIds: ['trading'], productIds: [] }, units, products)).toBe(false);
    expect(readsNothing({ departmentIds: [], productIds: ['termless'] }, units, products)).toBe(true);
  });

  it('reads a tool as words, and counts the terms a call read in', () => {
    expect(toolName('listObligations')).toBe('List obligations');
    expect(toolName('whatApplies')).toBe('What applies');
    expect(toolName('search')).toBe('Search');
    expect(scopeTermCount({ product_type: ['derivatives', 'securities'], activity: ['trading'] })).toBe(3);
  });
});
