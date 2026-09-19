import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it } from 'vitest';

import { hasProblemCode, NETWORK_PROBLEM_CODE, problemFrom, problemStatus } from './problem';

function axiosError(status: number | undefined, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const response = status === undefined ? undefined : ({ status, data, statusText: '', headers: {}, config } as AxiosResponse);
  return new AxiosError('x', String(status), config, undefined, response);
}

describe('problemFrom', () => {
  it('reads the problem details body with its code and the permission', () => {
    expect(problemFrom(axiosError(403, { title: 'Forbidden', status: 403, detail: 'Needs more', code: 'permission_denied', requiredPermission: 'members.manage' }))).toEqual({
      status: 403,
      title: 'Forbidden',
      detail: 'Needs more',
      code: 'permission_denied',
      requiredPermission: 'members.manage',
    });
  });

  it('keeps field errors and falls back to an http code when the body has none', () => {
    expect(problemFrom(axiosError(422, { errors: [{ field: 'email' }] }))).toEqual({ status: 422, title: '', detail: '', code: 'http_422', errors: [{ field: 'email' }] });
    expect(problemFrom(axiosError(500, 'oops'))).toEqual({ status: 500, title: '', detail: '', code: 'http_500' });
  });

  it('stands for a network failure when there is no response', () => {
    expect(problemFrom(axiosError(undefined, undefined))).toEqual({ status: 0, title: '', detail: '', code: NETWORK_PROBLEM_CODE });
  });

  it('ignores anything that is not an axios error', () => {
    expect(problemFrom(new Error('x'))).toBeNull();
    expect(problemFrom('x')).toBeNull();
    expect(problemStatus(new Error('x'))).toBeNull();
  });

  it('answers code and status questions', () => {
    const error = axiosError(409, { code: 'last_admin' });
    expect(hasProblemCode(error, 'last_admin')).toBe(true);
    expect(hasProblemCode(error, 'stale_write')).toBe(false);
    expect(problemStatus(error)).toBe(409);
  });
});
