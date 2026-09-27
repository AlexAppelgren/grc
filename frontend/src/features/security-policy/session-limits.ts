import type { SecurityPolicy } from '@/features/security-policy/types';
import { problemFrom } from '@/shared/utils/problem';

// The session-limit form's pure rules (ID-08, ADM-01). A field holds the text
// a person typed; empty goes back to the platform default (null), and the
// platform maximum is the server's to enforce, so a number above it is sent
// and its 422 above_platform_maximum is drawn under the field it names.

export type LimitField = 'sessionIdleMinutes' | 'sessionAbsoluteHours';

export interface LimitsDraft {
  sessionIdleMinutes: string;
  sessionAbsoluteHours: string;
}

/** The draft a form starts from: the limits in force, the platform default where the bank set none. */
export function draftOf(policy: SecurityPolicy): LimitsDraft {
  return {
    sessionIdleMinutes: String(policy.sessionIdleMinutes ?? policy.sessionIdleMinutesDefault),
    sessionAbsoluteHours: String(policy.sessionAbsoluteHours ?? policy.sessionAbsoluteHoursDefault),
  };
}

/** A whole number of at least 1, null for an empty field, or 'invalid'. */
export function parseLimit(text: string): number | null | 'invalid' {
  const trimmed = text.trim();
  if (trimmed === '') return null;
  if (!/^\d+$/.test(trimmed)) return 'invalid';
  const value = Number(trimmed);
  return value >= 1 && Number.isSafeInteger(value) ? value : 'invalid';
}

/** The fields a 422 above_platform_maximum names; empty for any other answer. */
export function fieldsAboveMaximum(error: unknown): LimitField[] {
  const problem = problemFrom(error);
  if (problem?.code !== 'above_platform_maximum' || problem.errors === undefined) return [];
  const fields: LimitField[] = [];
  for (const entry of problem.errors) {
    const field = typeof entry === 'object' && entry !== null ? (entry as Record<string, unknown>).field : undefined;
    if (field === 'sessionIdleMinutes' || field === 'sessionAbsoluteHours') fields.push(field);
  }
  return fields;
}
