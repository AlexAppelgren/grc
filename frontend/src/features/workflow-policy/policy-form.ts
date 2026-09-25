import type { WorkflowPolicy, WorkflowPolicyPatch } from '@/features/workflow-policy/types';
import { problemFrom } from '@/shared/utils/problem';

// The workflow form's rules, kept out of the component. The client checks
// mirror the server's (backend/apps/shared/models.py); the server stays the
// enforcer and its 422 lands under the field it names.

export const LEAD_DAYS_MAX = 90;
export const LEAD_DAYS_MAX_ENTRIES = 5;
export const ESCALATE_AFTER_DAYS_MAX = 90;
export const TRIAGE_TARGET_HOURS_MAX = 720;

/** The digest weekday is a kind (apps/shared/models.py `Weekday`), not a vocabulary. */
export const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;

export type DayListField = 'reminderDaysBefore' | 'reviewReminderDaysBefore';
export type WorkflowField = DayListField | 'escalateAfterDays' | 'escalateToRole' | 'digestWeekday' | 'triageTargetHours';

const FIELDS: readonly WorkflowField[] = ['reminderDaysBefore', 'reviewReminderDaysBefore', 'escalateAfterDays', 'escalateToRole', 'digestWeekday', 'triageTargetHours'];

/** `invalid`: out of range or malformed (validation_error); `unknown`: a key the bank does not have (unknown_key). */
export type FieldProblem = 'invalid' | 'unknown';
export type FieldErrors = Partial<Record<WorkflowField, FieldProblem>>;

/** The form's draft: the numbers stay as typed until Save checks them. */
export interface WorkflowDraft {
  reminderDaysBefore: number[];
  reviewReminderDaysBefore: number[];
  escalateAfterDays: string;
  escalateToRole: string;
  digestWeekday: string;
  triageTargetHours: string;
}

export function draftFrom(policy: WorkflowPolicy): WorkflowDraft {
  return {
    reminderDaysBefore: [...policy.reminderDaysBefore],
    reviewReminderDaysBefore: [...policy.reviewReminderDaysBefore],
    escalateAfterDays: String(policy.escalateAfterDays),
    escalateToRole: policy.escalateToRole.key,
    digestWeekday: policy.digestWeekday,
    triageTargetHours: String(policy.triageTargetHours),
  };
}

/** A whole number from 1 to `max` as typed, or null. */
export function wholeNumber(text: string, max: number): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const value = Number(text.trim());
  return value >= 1 && value <= max ? value : null;
}

/** Adds a typed day count to a list, largest first, or says why it cannot. */
export function addDay(days: readonly number[], text: string): { days: number[] } | { error: 'invalid' | 'duplicate' | 'full' } {
  if (days.length >= LEAD_DAYS_MAX_ENTRIES) return { error: 'full' };
  const value = wholeNumber(text, LEAD_DAYS_MAX);
  if (value === null) return { error: 'invalid' };
  if (days.includes(value)) return { error: 'duplicate' };
  return { days: [...days, value].sort((a, b) => b - a) };
}

/** The checks a draft must pass before it is sent. */
export function checkDraft(draft: WorkflowDraft): FieldErrors {
  const errors: FieldErrors = {};
  if (wholeNumber(draft.escalateAfterDays, ESCALATE_AFTER_DAYS_MAX) === null) errors.escalateAfterDays = 'invalid';
  if (wholeNumber(draft.triageTargetHours, TRIAGE_TARGET_HOURS_MAX) === null) errors.triageTargetHours = 'invalid';
  return errors;
}

/** The whole policy, as PATCH /tenant/workflow takes it. Call only on a draft `checkDraft` passed. */
export function bodyFrom(draft: WorkflowDraft): WorkflowPolicyPatch {
  return {
    reminderDaysBefore: draft.reminderDaysBefore,
    reviewReminderDaysBefore: draft.reviewReminderDaysBefore,
    escalateAfterDays: Number(draft.escalateAfterDays.trim()),
    escalateToRole: draft.escalateToRole,
    digestWeekday: draft.digestWeekday,
    triageTargetHours: Number(draft.triageTargetHours.trim()),
  };
}

/**
 * The server's 422, field by field, from its `code`: each entry of `errors`
 * names its field as a dotted path (`body.escalateAfterDays`,
 * `body.reminderDaysBefore.0`). Null when the error is not a 422 naming one
 * of the policy's fields; the screen then shows it whole.
 */
export function serverFieldErrors(error: unknown): FieldErrors | null {
  const problem = problemFrom(error);
  if (problem?.status !== 422) return null;
  const kind: FieldProblem = problem.code === 'unknown_key' ? 'unknown' : 'invalid';
  const errors: FieldErrors = {};
  for (const entry of problem.errors ?? []) {
    const path = typeof entry === 'object' && entry !== null ? (entry as Record<string, unknown>).field : undefined;
    const field = typeof path === 'string' ? FIELDS.find((name) => path.split('.').includes(name)) : undefined;
    if (field !== undefined) errors[field] = kind;
  }
  return Object.keys(errors).length > 0 ? errors : null;
}
