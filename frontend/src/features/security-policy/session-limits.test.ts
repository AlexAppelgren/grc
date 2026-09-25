import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it } from 'vitest';

import { draftOf, fieldsAboveMaximum, parseLimit } from '@/features/security-policy/session-limits';

const policy = {
  sessionIdleMinutes: null,
  sessionAbsoluteHours: 8,
  sessionIdleMinutesDefault: 30,
  sessionIdleMinutesMax: 480,
  sessionAbsoluteHoursDefault: 12,
  sessionAbsoluteHoursMax: 24,
  updatedAt: null,
  updatedBy: null,
};

function refusal(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const response = { status, data, statusText: '', headers: {}, config } as AxiosResponse;
  return new AxiosError(`status ${status}`, String(status), config, undefined, response);
}

describe('the session-limit form rules', () => {
  it('starts from the limits in force, the platform default where the bank set none', () => {
    expect(draftOf(policy)).toEqual({ sessionIdleMinutes: '30', sessionAbsoluteHours: '8' });
  });

  it('reads an empty field as the platform default and refuses anything but a whole number of at least 1', () => {
    expect(parseLimit('  ')).toBeNull();
    expect(parseLimit(' 15 ')).toBe(15);
    for (const text of ['0', '-1', '1.5', '1e3', 'ten', '99999999999999999999']) expect(parseLimit(text)).toBe('invalid');
  });

  it('names the fields a 422 above_platform_maximum names, and none for any other refusal', () => {
    const above = refusal(422, { code: 'above_platform_maximum', errors: [{ field: 'sessionAbsoluteHours', message: 'x' }, { field: 'other' }, 'junk'] });
    expect(fieldsAboveMaximum(above)).toEqual(['sessionAbsoluteHours']);
    expect(fieldsAboveMaximum(refusal(422, { code: 'validation_error', errors: [{ field: 'sessionIdleMinutes' }] }))).toEqual([]);
    expect(fieldsAboveMaximum(refusal(422, { code: 'above_platform_maximum' }))).toEqual([]);
    expect(fieldsAboveMaximum(new Error('offline'))).toEqual([]);
  });
});
