import { afterEach, describe, expect, it, vi } from 'vitest';

import { initialScope, storedScope, storeScope } from './scope';

const RETAIL = { id: 'unit-retail' };
const CARDS = { id: 'unit-cards' };

describe('initialScope', () => {
  it('opens a department named in the address, for anyone', () => {
    expect(initialScope('unit-x', 'mine', [])).toEqual({ scope: 'unit', unit: 'unit-x' });
  });

  it('opens a head on the remembered choice while they still head it', () => {
    expect(initialScope(null, 'mine', [RETAIL])).toEqual({ scope: 'mine' });
    expect(initialScope(null, CARDS.id, [RETAIL, CARDS])).toEqual({ scope: 'unit', unit: CARDS.id });
    expect(initialScope(null, 'unit-gone', [RETAIL])).toEqual({ scope: 'unit', unit: RETAIL.id });
  });

  it('opens a head on their department, and everyone else on their own work', () => {
    expect(initialScope(null, null, [RETAIL])).toEqual({ scope: 'unit', unit: RETAIL.id });
    expect(initialScope(null, null, [])).toEqual({ scope: 'mine' });
    expect(initialScope('', CARDS.id, [])).toEqual({ scope: 'mine' });
  });
});

describe('the remembered choice', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('round-trips through this device storage', () => {
    storeScope({ scope: 'unit', unit: RETAIL.id });
    expect(storedScope()).toBe(RETAIL.id);
    storeScope({ scope: 'mine' });
    expect(storedScope()).toBe('mine');
  });

  it('is simply absent when storage is refused', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    expect(() => storeScope({ scope: 'mine' })).not.toThrow();
    expect(storedScope()).toBeNull();
  });
});
