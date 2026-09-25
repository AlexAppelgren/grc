import { describe, expect, it } from 'vitest';

import { t } from '@/shared/i18n';

import { actionLabel, AUDIT_SUBJECT_TYPES, dayRange, diffRows, presentAuditEvent, snapshotValue, subjectTypeLabel } from './audit-presentation';

// The log is a ledger: the kind and the action are the row's own keys opened
// up, the diff is the snapshot's values as data, and the day range means the
// tenant's days, not UTC's.

const translate = (key: Parameters<typeof t>[0], vars?: Parameters<typeof t>[1]) => t(key, vars);

describe('audit presentation', () => {
  it('names a record kind and an action from the key, so a kind added later still reads', () => {
    expect(subjectTypeLabel('api_key')).toBe('api key');
    expect(subjectTypeLabel('footprint_change_request')).toBe('footprint change request');
    expect(actionLabel('api_key.created')).toBe('api key created');
    expect(AUDIT_SUBJECT_TYPES).toContain('api_key');
    expect(AUDIT_SUBJECT_TYPES).toContain('obligation');
    // FP-S10: watching a market is audited, so the log filters to it.
    expect(AUDIT_SUBJECT_TYPES).toContain('watched_market');
    // A case's moves are written under the kind the backend names, `change_case`.
    expect(AUDIT_SUBJECT_TYPES).toContain('change_case');
    expect(AUDIT_SUBJECT_TYPES).not.toContain('case');
    expect(new Set(AUDIT_SUBJECT_TYPES).size).toBe(AUDIT_SUBJECT_TYPES.length);
  });

  it('pills the record kind as a neutral fact and marks a completed passkey step-up', () => {
    expect(presentAuditEvent({ subjectType: 'membership', steppedUp: false }, translate)).toEqual([
      { key: 'subject:membership', label: 'membership', tone: 'information', order: 0 },
    ]);
    expect(presentAuditEvent({ subjectType: 'api_key', steppedUp: true }, translate)).toEqual([
      { key: 'subject:api_key', label: 'api key', tone: 'information', order: 0 },
      { key: 'stepped-up', label: 'Confirmed with a passkey', tone: 'positive', order: 1 },
    ]);
  });

  it('shows a value as data: a string as written, anything else as its JSON, an absent field as nothing', () => {
    expect(snapshotValue('Reader')).toBe('Reader');
    expect(snapshotValue(undefined)).toBeNull();
    expect(snapshotValue(null)).toBe('null');
    expect(snapshotValue(4)).toBe('4');
    expect(snapshotValue(false)).toBe('false');
    expect(snapshotValue(['a', 'b'])).toBe('["a","b"]');
    expect(snapshotValue({ en: 'Custody' })).toBe('{"en":"Custody"}');
  });

  it('diffs only the fields that changed, in field order, either side of the change', () => {
    expect(diffRows({ name: 'Old', scopes: ['a'], keep: 'same' }, { name: 'New', scopes: ['a'], added: 2 })).toEqual([
      { field: 'added', before: null, after: '2' },
      { field: 'keep', before: 'same', after: null },
      { field: 'name', before: 'Old', after: 'New' },
    ]);
    expect(diffRows({}, {})).toEqual([]);
  });

  it('turns a pair of days into the instants the tenant means, with the last day inside the range', () => {
    // Stockholm is two hours ahead in September, so its day starts at 22:00 UTC the evening before.
    expect(dayRange('2026-09-19', '2026-09-19', 'Europe/Stockholm')).toEqual({
      from: '2026-09-18T22:00:00.000Z',
      to: '2026-09-19T22:00:00.000Z',
    });
    // A zone behind UTC starts its day later, never earlier.
    expect(dayRange('2026-09-19', '', 'America/New_York')).toEqual({ from: '2026-09-19T04:00:00.000Z', to: undefined });
    expect(dayRange('', '2026-12-31', 'UTC')).toEqual({ from: undefined, to: '2027-01-01T00:00:00.000Z' });
    expect(dayRange('', '', 'Europe/Stockholm')).toEqual({ from: undefined, to: undefined });
    // A half-typed day is no bound at all, rather than an invalid instant.
    expect(dayRange('2026-09', '20', 'Europe/Stockholm')).toEqual({ from: undefined, to: undefined });
  });
});
