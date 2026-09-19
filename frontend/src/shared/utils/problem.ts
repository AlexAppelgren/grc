import { isAxiosError } from 'axios';

// The one error shape (playbook 4.4): RFC 9457 problem details with a
// machine-readable `code`. Screens branch on `code` and status, never on
// `detail`; `detail` is shown as the server wrote it.

export interface Problem {
  status: number;
  title: string;
  detail: string;
  code: string;
  requiredPermission?: string;
  errors?: unknown[];
}

/** `status` 0 and code `network` stand for "the server did not answer". */
export const NETWORK_PROBLEM_CODE = 'network';

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

export function problemFrom(error: unknown): Problem | null {
  if (!isAxiosError(error)) return null;
  const response = error.response;
  if (response === undefined) {
    return { status: 0, title: '', detail: '', code: NETWORK_PROBLEM_CODE };
  }
  const body: unknown = response.data;
  const record = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
  const requiredPermission = asString(record.requiredPermission);
  return {
    status: response.status,
    title: asString(record.title),
    detail: asString(record.detail),
    code: asString(record.code) || `http_${response.status}`,
    ...(requiredPermission === '' ? {} : { requiredPermission }),
    ...(Array.isArray(record.errors) ? { errors: record.errors } : {}),
  };
}

export function hasProblemCode(error: unknown, code: string): boolean {
  return problemFrom(error)?.code === code;
}

export function problemStatus(error: unknown): number | null {
  return problemFrom(error)?.status ?? null;
}
