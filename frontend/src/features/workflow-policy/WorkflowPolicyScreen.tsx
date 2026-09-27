'use client';

import { useState, type FormEvent, type KeyboardEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useRoles, useTenant } from '@/features/tenant-admin/hooks';
import type { RoleRef, Tenant, TenantRole } from '@/features/tenant-admin/types';
import { useUpdateWorkflowPolicy } from '@/features/workflow-policy/hooks';
import {
  addDay,
  bodyFrom,
  checkDraft,
  draftFrom,
  ESCALATE_AFTER_DAYS_MAX,
  LEAD_DAYS_MAX,
  LEAD_DAYS_MAX_ENTRIES,
  serverFieldErrors,
  TRIAGE_TARGET_HOURS_MAX,
  WEEKDAYS,
  type DayListField,
  type FieldErrors,
  type WorkflowDraft,
} from '@/features/workflow-policy/policy-form';
import type { MessageKey, Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// Workflow (design/screens/admin-workflow.html, COL-02, TEN-01): the bank's
// reminder lead days, escalation threshold and role, digest weekday and triage
// target, each with its unit and the platform default beside it. Saved whole
// through PATCH /tenant/workflow under workflow.manage; no step-up, no four
// eyes. Client checks mirror the server's, whose 422 lands under the field it
// names, chosen by its code.

function weekdayLabel(key: string, t: Translate): string {
  return (WEEKDAYS as readonly string[]).includes(key) ? t(`workflow.weekday.${key}` as MessageKey) : key;
}

/** The bank's active roles, plus the current and the default target when neither is among them (a retired role still shows what it points at). */
export function roleOptions(roles: readonly TenantRole[] | undefined, tenant: Tenant): RoleRef[] {
  const options = new Map<string, RoleRef>((roles ?? []).map((role) => [role.key, { key: role.key, kind: role.kind, label: role.label }]));
  for (const role of [tenant.workflow.escalateToRole, tenant.workflowDefaults.escalateToRole]) {
    if (!options.has(role.key)) options.set(role.key, role);
  }
  return [...options.values()];
}

function DayList({
  id,
  label,
  hint,
  addLabel,
  days,
  problem,
  onChange,
}: {
  id: DayListField;
  label: string;
  hint: string;
  addLabel: string;
  days: number[];
  problem: string | undefined;
  onChange: (days: number[]) => void;
}) {
  const t = useT();
  const [typed, setTyped] = useState('');
  const [refusal, setRefusal] = useState<string | undefined>(undefined);
  const full = days.length >= LEAD_DAYS_MAX_ENTRIES;
  const error = refusal ?? problem;

  const add = () => {
    const result = addDay(days, typed);
    if ('days' in result) {
      setTyped('');
      setRefusal(undefined);
      onChange(result.days);
    } else if (result.error === 'duplicate') {
      setRefusal(t('workflow.days.duplicate', { days: t('workflow.days', { count: Number(typed.trim()) }) }));
    } else {
      setRefusal(t('workflow.wholeNumber', { max: LEAD_DAYS_MAX }));
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    add();
  };

  return (
    <div className="mb-3 grid gap-1.5" data-workflow-field={id}>
      <span id={`${id}-label`} className="font-medium">
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-2" role="group" aria-labelledby={`${id}-label`} aria-describedby={`${id}-hint`}>
        {days.map((day) => (
          <span key={day} data-day={day} className={cn('inline-flex h-8 items-center gap-1 rounded-control border border-line-strong bg-neutral-soft pl-3 font-medium tabular-nums', days.length > 1 ? 'pr-1' : 'pr-3')}>
            {t('workflow.days', { count: day })}
            {/* The last reminder stays: the server refuses an empty list. */}
            {days.length > 1 ? (
              <button
                type="button"
                className="inline-flex size-6 items-center justify-center rounded-[4px] text-muted hover:hover-fill"
                aria-label={t('workflow.days.remove', { days: t('workflow.days', { count: day }) })}
                onClick={() => onChange(days.filter((d) => d !== day))}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4 fill-none stroke-current" strokeWidth={1.75} strokeLinecap="round">
                  <path d="M7 7l10 10M17 7L7 17" />
                </svg>
              </button>
            ) : null}
          </span>
        ))}
        <span className="flex items-center gap-2">
          <TextInput
            type="number"
            inputMode="numeric"
            min={1}
            max={LEAD_DAYS_MAX}
            className="h-8 w-[72px]"
            aria-label={addLabel}
            aria-invalid={refusal !== undefined}
            aria-describedby={error !== undefined ? `${id}-error` : undefined}
            disabled={full}
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
              setRefusal(undefined);
            }}
            onKeyDown={onKeyDown}
          />
          <Button variant="outline" size="small" disabled={full} onClick={add}>
            {t('workflow.days.add')}
          </Button>
        </span>
      </div>
      <span id={`${id}-hint`} className="text-meta text-muted">
        {full ? t('workflow.days.full', { entries: LEAD_DAYS_MAX_ENTRIES }) : hint}
      </span>
      {error !== undefined ? (
        <span id={`${id}-error`} role="alert" className="text-meta text-negative">
          {error}
        </span>
      ) : null}
    </div>
  );
}

function NumberWithUnit({ id, value, max, unit, invalid, onChange }: { id: string; value: string; max: number; unit: string; invalid: boolean; onChange: (value: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <TextInput
        id={id}
        type="number"
        inputMode="numeric"
        min={1}
        max={max}
        className="w-[88px] tabular-nums"
        aria-invalid={invalid}
        aria-describedby={invalid ? `${id}-hint ${id}-error` : `${id}-hint`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="text-muted">{unit}</span>
    </div>
  );
}

function WorkflowForm({ tenant, roles }: { tenant: Tenant; roles: RoleRef[] }) {
  const t = useT();
  const update = useUpdateWorkflowPolicy();
  const defaults = tenant.workflowDefaults;
  const [draft, setDraft] = useState<WorkflowDraft>(() => draftFrom(tenant.workflow));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saved, setSaved] = useState(false);

  const change = <K extends keyof WorkflowDraft>(field: K, value: WorkflowDraft[K]) => {
    setDraft((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    setSaved(false);
  };

  const withDefault = (hint: string, value: string) => t('workflow.withDefault', { hint, value });
  const days = (count: number) => t('workflow.days', { count });
  const dayList = (list: readonly number[]) => list.map(days).join(', ');
  const dayListProblem = (field: DayListField) =>
    errors[field] !== undefined ? t('workflow.days.invalid', { entries: LEAD_DAYS_MAX_ENTRIES, max: LEAD_DAYS_MAX }) : undefined;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    const refused = checkDraft(draft);
    setErrors(refused);
    if (Object.keys(refused).length > 0) return;
    update.mutate(bodyFrom(draft), {
      onSuccess: (answer) => {
        setDraft(draftFrom(answer.workflow));
        setSaved(true);
      },
      onError: (error) => setErrors(serverFieldErrors(error) ?? {}),
    });
  };

  const reset = () => {
    setDraft(draftFrom(defaults));
    setErrors({});
    setSaved(false);
  };

  const serverRefusedFields = update.isError && serverFieldErrors(update.error) !== null;
  const leadHint = { entries: LEAD_DAYS_MAX_ENTRIES, max: LEAD_DAYS_MAX };

  return (
    <form onSubmit={submit} noValidate aria-busy={update.isPending} className="grid max-w-[640px] gap-4" data-workflow-form="">
      <Panel title={t('workflow.reminders')} className="mb-0">
        <DayList
          id="reminderDaysBefore"
          label={t('workflow.due.label')}
          hint={withDefault(t('workflow.due.hint', leadHint), dayList(defaults.reminderDaysBefore))}
          addLabel={t('workflow.due.add')}
          days={draft.reminderDaysBefore}
          problem={dayListProblem('reminderDaysBefore')}
          onChange={(value) => change('reminderDaysBefore', value)}
        />
        <DayList
          id="reviewReminderDaysBefore"
          label={t('workflow.review.label')}
          hint={withDefault(t('workflow.review.hint', leadHint), dayList(defaults.reviewReminderDaysBefore))}
          addLabel={t('workflow.review.add')}
          days={draft.reviewReminderDaysBefore}
          problem={dayListProblem('reviewReminderDaysBefore')}
          onChange={(value) => change('reviewReminderDaysBefore', value)}
        />
      </Panel>

      <Panel title={t('workflow.escalation')} className="mb-0">
        <div data-workflow-field="escalateAfterDays">
          <Field
            id="workflow-escalate-after"
            label={t('workflow.escalateAfter.label')}
            hint={withDefault(t('workflow.escalateAfter.hint', { max: ESCALATE_AFTER_DAYS_MAX }), days(defaults.escalateAfterDays))}
            error={errors.escalateAfterDays !== undefined ? t('workflow.wholeNumber', { max: ESCALATE_AFTER_DAYS_MAX }) : undefined}
          >
            <NumberWithUnit
              id="workflow-escalate-after"
              value={draft.escalateAfterDays}
              max={ESCALATE_AFTER_DAYS_MAX}
              unit={t('workflow.escalateAfter.unit')}
              invalid={errors.escalateAfterDays !== undefined}
              onChange={(value) => change('escalateAfterDays', value)}
            />
          </Field>
        </div>
        <div data-workflow-field="escalateToRole">
          <Field
            id="workflow-escalate-to"
            label={t('workflow.escalateTo.label')}
            hint={withDefault(t('workflow.escalateTo.hint'), defaults.escalateToRole.label)}
            error={errors.escalateToRole !== undefined ? t('workflow.escalateTo.unknown') : undefined}
          >
            <Select
              id="workflow-escalate-to"
              className="max-w-[320px]"
              aria-invalid={errors.escalateToRole !== undefined}
              aria-describedby={errors.escalateToRole !== undefined ? 'workflow-escalate-to-hint workflow-escalate-to-error' : 'workflow-escalate-to-hint'}
              value={draft.escalateToRole}
              onChange={(event) => change('escalateToRole', event.target.value)}
            >
              {roles.map((role) => (
                <option key={role.key} value={role.key}>
                  {role.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Panel>

      <Panel title={t('workflow.digestAndTriage')} className="mb-0">
        <div data-workflow-field="digestWeekday">
          <Field
            id="workflow-digest-day"
            label={t('workflow.digest.label')}
            hint={withDefault(t('workflow.digest.hint', { timezone: tenant.timezone }), weekdayLabel(defaults.digestWeekday, t))}
            error={errors.digestWeekday !== undefined ? t('workflow.digest.unknown') : undefined}
          >
            <Select
              id="workflow-digest-day"
              className="max-w-[320px]"
              aria-invalid={errors.digestWeekday !== undefined}
              aria-describedby={errors.digestWeekday !== undefined ? 'workflow-digest-day-hint workflow-digest-day-error' : 'workflow-digest-day-hint'}
              value={draft.digestWeekday}
              onChange={(event) => change('digestWeekday', event.target.value)}
            >
              {WEEKDAYS.map((day) => (
                <option key={day} value={day}>
                  {weekdayLabel(day, t)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div data-workflow-field="triageTargetHours">
          <Field
            id="workflow-triage"
            label={t('workflow.triage.label')}
            hint={withDefault(t('workflow.triage.hint', { max: TRIAGE_TARGET_HOURS_MAX }), t('workflow.hours', { count: defaults.triageTargetHours }))}
            error={errors.triageTargetHours !== undefined ? t('workflow.wholeNumber', { max: TRIAGE_TARGET_HOURS_MAX }) : undefined}
          >
            <NumberWithUnit
              id="workflow-triage"
              value={draft.triageTargetHours}
              max={TRIAGE_TARGET_HOURS_MAX}
              unit={t('workflow.triage.unit')}
              invalid={errors.triageTargetHours !== undefined}
              onChange={(value) => change('triageTargetHours', value)}
            />
          </Field>
        </div>
      </Panel>

      <div>
        {update.isError && !serverRefusedFields ? <ProblemAlert error={update.error} /> : null}
        {saved && !update.isPending ? <StatusLine tone="positive">{t('common.saved')}</StatusLine> : null}
        <ButtonBar className="mt-2">
          <Button variant="outline" onClick={reset} disabled={update.isPending}>
            {t('workflow.reset')}
          </Button>
          <Button type="submit" disabled={update.isPending}>
            {t('common.save')}
          </Button>
        </ButtonBar>
      </div>
    </form>
  );
}

export function WorkflowPolicyScreen() {
  const t = useT();
  const tenant = useTenant();
  const roles = useRoles();

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('workflow.title')} lede={t('workflow.lede')} />
      {tenant.isPending || roles.isPending ? (
        <LoadingState />
      ) : tenant.isError ? (
        <ErrorState title={t('workflow.errorTitle')} onRetry={() => void tenant.refetch()} />
      ) : (
        // Keyed on the id: the form's own state is the draft.
        <WorkflowForm key={tenant.data.id} tenant={tenant.data} roles={roleOptions(roles.data, tenant.data)} />
      )}
    </>
  );
}
