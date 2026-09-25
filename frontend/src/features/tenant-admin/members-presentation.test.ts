import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import {
  humaniseKey,
  loginMethodText,
  presentApiKey,
  presentInvitation,
  presentLoginEvent,
  presentMember,
  presentPermissions,
  presentRole,
} from './members-presentation';

const t = createT('en');
const now = new Date('2026-09-19T10:00:00Z');
const roles = [
  { key: 'compliance_officer', kind: 'system', label: 'Compliance officer' },
  { key: 'reader', kind: 'system', label: 'Reader' },
];

describe('presentMember', () => {
  it('shows the role labels from the rows as information pills, then the status', () => {
    expect(presentMember({ status: 'invited', roles }, t).map((p) => [p.label, p.tone, p.order])).toEqual([
      ['Compliance officer', 'information', 10],
      ['Reader', 'information', 11],
      ['Awaiting enrolment', 'warning', 50],
    ]);
  });

  it('marks a deactivated member as a neutral fact and an active one with nothing', () => {
    expect(presentMember({ status: 'deactivated', roles: [] }, t)).toEqual([{ key: 'status:deactivated', label: 'Deactivated', tone: 'information', order: 50 }]);
    expect(presentMember({ status: 'active', roles: [] }, t)).toEqual([]);
    expect(presentMember({ status: 'later' as 'active', roles: [] }, t)).toEqual([]);
  });
});

describe('presentInvitation', () => {
  const base = { kind: 'invite' as const, roles: [roles[1]!], status: 'pending' as const };

  it('is awaiting enrolment while pending', () => {
    expect(presentInvitation(base, t).map((p) => [p.label, p.tone])).toEqual([
      ['Reader', 'information'],
      ['Awaiting enrolment', 'warning'],
    ]);
  });

  it('labels accepted, revoked and expired from the status kind', () => {
    expect(presentInvitation({ ...base, status: 'accepted' }, t).at(-1)).toMatchObject({ label: 'Accepted', tone: 'positive' });
    expect(presentInvitation({ ...base, status: 'revoked' }, t).at(-1)).toMatchObject({ label: 'Revoked', tone: 'information' });
    expect(presentInvitation({ ...base, status: 'expired' }, t).at(-1)).toEqual({ key: 'status:expired', label: 'Expired', tone: 'information', order: 50 });
    expect(presentInvitation({ ...base, status: 'later' as 'pending' }, t)).toHaveLength(1);
  });

  it('prefixes a re-enrolment invitation with its kind', () => {
    expect(presentInvitation({ ...base, kind: 'reenrolment' }, t).map((p) => p.label)).toEqual(['Re-enrolment', 'Reader', 'Awaiting enrolment']);
  });
});

describe('presentRole and presentPermissions', () => {
  it('flags a system role as a neutral fact', () => {
    expect(presentRole({ isSystem: true }, t)).toEqual([{ key: 'role:system', label: 'System role', tone: 'information', order: 5 }]);
    expect(presentRole({ isSystem: false }, t)).toEqual([]);
  });

  it('renders permissions as their grant name in plain words', () => {
    expect(presentPermissions(['cases.signoff', 'library_vocab.manage']).map((p) => [p.label, p.tone, p.order])).toEqual([
      ['cases signoff', 'information', 10],
      ['library vocab manage', 'information', 11],
    ]);
    expect(humaniseKey('search:read')).toBe('search read');
  });
});

describe('presentApiKey', () => {
  const base = { scopes: ['tenant:read', 'search:read'], revokedAt: null, expiresAt: null };

  it('lists scopes as neutral pills', () => {
    expect(presentApiKey(base, t, now).map((p) => p.label)).toEqual(['tenant read', 'search read']);
  });

  it('puts revoked or expired first, revoked winning', () => {
    expect(presentApiKey({ ...base, revokedAt: '2026-09-19T09:00:00Z', expiresAt: '2026-01-01T00:00:00Z' }, t, now)[0]).toEqual({ key: 'status:revoked', label: 'Revoked', tone: 'information', order: 5 });
    expect(presentApiKey({ ...base, expiresAt: '2026-01-01T00:00:00Z' }, t, now)[0]).toEqual({ key: 'status:expired', label: 'Expired', tone: 'warning', order: 5 });
    expect(presentApiKey({ ...base, expiresAt: '2027-01-01T00:00:00Z' }, t, now)).toHaveLength(2);
  });
});

describe('presentLoginEvent and loginMethodText', () => {
  it('labels every known event kind from the catalog with its tone', () => {
    expect(presentLoginEvent({ event: 'signin', success: true }, t)).toEqual([{ key: 'event:signin', label: 'Signed in', tone: 'positive', order: 5 }]);
    expect(presentLoginEvent({ event: 'signin_failed', success: false }, t)[0]).toMatchObject({ label: 'Sign-in failed', tone: 'negative' });
    expect(presentLoginEvent({ event: 'code_refused_enrolled', success: false }, t)[0]).toMatchObject({ label: 'Code refused, already enrolled', tone: 'warning' });
    expect(presentLoginEvent({ event: 'reenrolment_issued', success: true }, t)[0]).toMatchObject({ label: 'Enrolment re-issued', tone: 'information' });
    expect(presentLoginEvent({ event: 'key_created', success: true }, t)[0]).toMatchObject({ label: 'Key created', tone: 'information' });
    expect(presentLoginEvent({ event: 'key_scopes_withheld', success: false }, t)[0]).toMatchObject({ label: 'Scopes withheld from key', tone: 'warning' });
  });

  it('falls back to the kind in plain words with a tone from success', () => {
    expect(presentLoginEvent({ event: 'ip_blocked', success: false }, t)[0]).toMatchObject({ label: 'ip blocked', tone: 'negative' });
    expect(presentLoginEvent({ event: 'new_thing', success: true }, t)[0]).toMatchObject({ label: 'new thing', tone: 'information' });
  });

  it('names the method', () => {
    expect(loginMethodText('passkey', t)).toBe('Passkey');
    expect(loginMethodText('email_code', t)).toBe('Email code');
    expect(loginMethodText('magic', t)).toBe('magic');
  });
});
