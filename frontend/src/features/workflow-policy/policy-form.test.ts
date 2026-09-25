import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it } from 'vitest';

import { addDay, bodyFrom, checkDraft, draftFrom, serverFieldErrors, wholeNumber } from '@/features/workflow-policy/policy-form';

// The workflow form's rules (COL-02): the client refuses what the server
// would refuse before sending, and reads the server's 422 field by field
// from its code, never from its wording.

const policy = {
  reminderDaysBefore: [7, 3],
  reviewReminderDaysBefore: [30],
  escalateAfterDays: 10,
  escalateToRole: { key: 'compliance_officer', kind: null, label: 'Compliance officer' },
  digestWeekday: 'monday',
  triageTargetHours: 48,
};

function answered(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const response = { data, status, statusText: String(status), headers: {}, config } as AxiosResponse;
  return new AxiosError(`status ${status}`, String(status), config, undefined, response);
}

describe('the workflow form rules', () => {
  it('takes whole numbers in range only', () => {
    expect(wholeNumber('5', 90)).toBe(5);
    expect(wholeNumber(' 90 ', 90)).toBe(90);
    for (const text of ['0', '91', '', '2.5', '-1', 'x', '1e2']) expect(wholeNumber(text, 90)).toBeNull();
  });

  it('adds a day largest first, and refuses a repeat, a bad number and a sixth entry', () => {
    expect(addDay([7, 3], '14')).toEqual({ days: [14, 7, 3] });
    expect(addDay([7, 3], '1')).toEqual({ days: [7, 3, 1] });
    expect(addDay([7, 3], '3')).toEqual({ error: 'duplicate' });
    expect(addDay([7, 3], '91')).toEqual({ error: 'invalid' });
    expect(addDay([30, 14, 7, 3, 1], '2')).toEqual({ error: 'full' });
  });

  it('sends the whole policy, the role and the weekday as keys', () => {
    const draft = draftFrom(policy);
    expect(checkDraft(draft)).toEqual({});
    expect(bodyFrom({ ...draft, escalateAfterDays: ' 12 ' })).toEqual({
      reminderDaysBefore: [7, 3],
      reviewReminderDaysBefore: [30],
      escalateAfterDays: 12,
      escalateToRole: 'compliance_officer',
      digestWeekday: 'monday',
      triageTargetHours: 48,
    });
    expect(checkDraft({ ...draft, escalateAfterDays: '120', triageTargetHours: '0' })).toEqual({ escalateAfterDays: 'invalid', triageTargetHours: 'invalid' });
  });

  it('reads a 422 per field from its code and leaves anything else whole', () => {
    expect(serverFieldErrors(answered(422, { code: 'validation_error', errors: [{ field: 'body.reminderDaysBefore.0', message: 'x' }, { field: 'body.triageTargetHours', message: 'y' }] }))).toEqual({
      reminderDaysBefore: 'invalid',
      triageTargetHours: 'invalid',
    });
    expect(serverFieldErrors(answered(422, { code: 'unknown_key', errors: [{ field: 'escalateToRole', message: 'x' }] }))).toEqual({ escalateToRole: 'unknown' });
    expect(serverFieldErrors(answered(422, { code: 'validation_error', errors: [{ field: 'body.surprise', message: 'x' }] }))).toBeNull();
    expect(serverFieldErrors(answered(403, { code: 'permission_denied', requiredPermission: 'workflow.manage' }))).toBeNull();
    expect(serverFieldErrors(new Error('offline'))).toBeNull();
  });
});
