import { describe, expect, it } from 'vitest';

import { isLiveToken, presentToken } from '@/features/personal-tokens/presentation';
import type { Translate } from '@/shared/i18n';

// A token's pills from its own facts (me-tokens.html): no kind pill, Revoked
// before Expired, then its scopes, every tone from a slot or a state.

const t = ((key: string) => key) as Translate;
const now = new Date('2026-09-25T12:00:00Z');
const base = { scopes: ['library:read', 'tenant:read'], revokedAt: null, expiresAt: '2026-12-19T23:59:59Z' };

describe('presentToken', () => {
  it('shows a live token as its scopes alone', () => {
    expect(presentToken(base, t, now)).toEqual([
      { key: 'scope:library:read', label: 'library read', tone: 'information', order: 1 },
      { key: 'scope:tenant:read', label: 'tenant read', tone: 'information', order: 2 },
    ]);
    expect(isLiveToken(base, now)).toBe(true);
  });

  it('puts Expired, a warning, first once the expiry has passed', () => {
    const expired = { ...base, expiresAt: '2026-08-30T23:59:59Z' };
    expect(presentToken(expired, t, now)[0]).toEqual({ key: 'state:expired', label: 'me.tokens.expired', tone: 'warning', order: 0 });
    expect(isLiveToken(expired, now)).toBe(false);
  });

  it('reads a revoked token as Revoked, information, whatever its expiry', () => {
    const revoked = { ...base, revokedAt: '2026-09-10T08:00:00Z', expiresAt: '2026-08-30T23:59:59Z' };
    const pills = presentToken(revoked, t, now);
    expect(pills[0]).toEqual({ key: 'state:revoked', label: 'me.tokens.revoked', tone: 'information', order: 0 });
    expect(pills.filter((p) => p.key.startsWith('state:'))).toHaveLength(1);
    expect(isLiveToken(revoked, now)).toBe(false);
  });
});
