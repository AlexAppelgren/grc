'use client';

import { useState, type FormEvent } from 'react';

import { Pill } from '@/components/ui/Pill';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel } from '@/components/ui/Panel';
import { Notice } from '@/components/ui/Notice';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { daysLeftText, presentOverdue } from '@/features/cases/case-presentation';
import { staleWriteOf, useAddAction, useCaseActions, useDeleteAction, useReloadCase, useUpdateAction } from '@/features/cases/hooks';
import type { CaseAction, CaseCategory, CasePanelProps } from '@/features/cases/types';
import { useFormatContext } from '@/features/identity/hooks';
import { CASES_WORK } from '@/features/watch/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';
import { hasProblemCode, problemFrom } from '@/shared/utils/problem';

// The case's actions (design/screens/tenant-change.html, "Actions"; CAS-04).
// Owner, due date, days left and the overdue pill; the add row and Remove for
// `cases.work`, the completion box for `cases.contribute`, so a contributor
// completes and reopens but never adds or removes. While the case waits for
// sign-off every control is off and the panel says why; a stale tab's 409
// `actions_locked`, a 409 `stale_write` and the cap's 409 render where the
// write was made, from the server's answer. Send as tickets is chunk 13's.

export const CASES_CONTRIBUTE = 'cases.contribute';

/** The categories whose actions can change; from sign-off on they are locked. */
export const WORKED: readonly CaseCategory[] = ['assessing', 'implementing'];

/** The tenant-local calendar day, as UTC midnight, for `daysUntil`. */
export function tenantToday(timeZone: string, now: Date = new Date()): Date {
  const [year, month, day] = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now).split('-').map(Number);
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1));
}

/** A write the server refused: a lock or a stale version offers a reload, anything else is its own answer. */
function WriteRefusal({ error, changeId }: { error: unknown; changeId: string }) {
  const t = useT();
  const reload = useReloadCase(changeId);
  if (error === null || error === undefined) return null;
  const locked = hasProblemCode(error, 'actions_locked');
  if (!locked && staleWriteOf(error) === null) return <ProblemAlert error={error} />;
  return (
    <p role="alert" className="mt-2.5 text-meta text-negative" data-problem-code={locked ? 'actions_locked' : 'stale_write'}>
      {locked ? t('caseActions.lockedRefusal') : t('cases.staleWrite.body')}{' '}
      <button type="button" className="underline" onClick={() => void reload()}>
        {locked ? t('caseActions.reload') : t('cases.staleWrite.reload')}
      </button>
    </p>
  );
}

function fieldErrorOf(error: unknown, field: string): boolean {
  const problem = problemFrom(error);
  if (problem?.status !== 422 || problem.errors === undefined) return false;
  return problem.errors.some((entry) => typeof entry === 'object' && entry !== null && String((entry as { field?: unknown }).field).endsWith(field));
}

function AddActionRow({ changeId, caseVersion, ownerName }: { changeId: string; caseVersion: number; ownerName: string | null }) {
  const t = useT();
  const add = useAddAction(changeId, caseVersion);
  const [title, setTitle] = useState('');
  const [dueDate, setDueDate] = useState('');
  const titleError = fieldErrorOf(add.error, 'title');
  const dueError = fieldErrorOf(add.error, 'dueDate');

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate(
      { title, dueDate },
      {
        onSuccess: () => {
          setTitle('');
          setDueDate('');
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="mt-3 border-t border-line pt-3" data-add-action="">
      <div className="grid gap-x-3 sm:grid-cols-[1fr_180px]">
        <Field id="action-title" label={t('caseActions.newTitle')} error={titleError ? t('caseActions.titleRequired') : undefined}>
          <TextInput
            id="action-title"
            value={title}
            placeholder={t('caseActions.newTitlePlaceholder')}
            aria-invalid={titleError || undefined}
            aria-describedby="action-title-hint"
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>
        <Field id="action-due" label={t('caseActions.newDue')} error={dueError ? t('caseActions.dueRequired') : undefined}>
          <TextInput id="action-due" type="date" value={dueDate} aria-invalid={dueError || undefined} onChange={(event) => setDueDate(event.target.value)} />
        </Field>
      </div>
      <p id="action-title-hint" className="text-meta text-muted">
        {ownerName === null ? t('caseActions.ownerHintNone') : t('caseActions.ownerHint', { name: ownerName })}
      </p>
      {titleError || dueError ? null : <WriteRefusal error={add.error} changeId={changeId} />}
      <ButtonBar className="mt-2">
        <Button type="submit" disabled={add.isPending}>
          {t('caseActions.add')}
        </Button>
      </ButtonBar>
    </form>
  );
}

function ActionRow({ action, today, canComplete, canRemove, busy, onDone, onRemove }: {
  action: CaseAction;
  today: Date;
  canComplete: boolean;
  canRemove: boolean;
  busy: boolean;
  onDone: (done: boolean) => void;
  onRemove: () => void;
}) {
  const t = useT();
  const ctx = useFormatContext();
  const overdue = presentOverdue(action, today, t);
  const left = daysLeftText(action, today, t);
  const boxId = `action-${action.id}`;
  return (
    <div className="flex items-start gap-2.5 border-b border-line py-2.5 last:border-b-0" data-action={action.id} data-done={action.done || undefined}>
      <input
        id={boxId}
        type="checkbox"
        className="mt-1 size-4 accent-button"
        checked={action.done}
        disabled={!canComplete || busy}
        aria-describedby={`${boxId}-meta`}
        onChange={(event) => onDone(event.target.checked)}
      />
      <div className="min-w-0 flex-1">
        <label htmlFor={boxId} className={action.done ? 'font-medium text-muted line-through' : 'font-medium'}>
          {action.title}
        </label>
        <Meta className="mt-1">
          <span id={`${boxId}-meta`} className="contents">
            <span>{action.owner.name}</span>
            <span className="tabular-nums">{t('caseActions.due', { date: formatDate(action.dueDate, ctx) })}</span>
            {overdue === null ? null : <Pill tone={overdue.tone}>{overdue.label}</Pill>}
            {left === null ? null : <span className="tabular-nums">{left}</span>}
            {action.done && action.doneAt !== null ? (
              <span>{t('caseActions.doneBy', { date: formatDate(action.doneAt, ctx), name: action.doneBy?.name ?? '' })}</span>
            ) : null}
          </span>
        </Meta>
      </div>
      {canRemove ? (
        <Button variant="ghost" size="small" onClick={onRemove}>
          {t('caseActions.remove')}
        </Button>
      ) : null}
    </div>
  );
}

export function ActionsPanel({ change, workflow }: CasePanelProps) {
  const t = useT();
  const ctx = useFormatContext();
  const permissions = usePermissions() ?? [];
  const actions = useCaseActions(change.id);
  const update = useUpdateAction(change.id);
  const remove = useDeleteAction(change.id);
  const [removing, setRemoving] = useState<CaseAction | null>(null);

  const worked = WORKED.includes(workflow.category);
  const canWork = worked && permissions.includes(CASES_WORK);
  const canComplete = worked && permissions.includes(CASES_CONTRIBUTE);
  const today = tenantToday(ctx.timeZone);

  function confirmRemove() {
    if (removing === null) return;
    remove.mutate(removing, { onSettled: () => setRemoving(null) });
  }

  let body;
  if (actions.isPending) body = <LoadingState />;
  else if (actions.isError) body = <ErrorState title={t('caseActions.loadError')} onRetry={() => void actions.refetch()} />;
  else {
    const items = actions.data.items;
    body = (
      <>
        {items.length === 0 ? (
          <div className="py-4 text-center text-muted" data-actions-empty="">
            <h3 className="text-fg">{t('caseActions.empty.title')}</h3>
            <p className="mt-1">{t('caseActions.empty.body')}</p>
          </div>
        ) : (
          <div>
            {items.map((action) => (
              <ActionRow
                key={action.id}
                action={action}
                today={today}
                canComplete={canComplete}
                canRemove={canWork}
                busy={update.isPending}
                onDone={(done) => update.mutate({ action, patch: { done } })}
                onRemove={() => setRemoving(action)}
              />
            ))}
          </div>
        )}
        <WriteRefusal error={update.error ?? remove.error} changeId={change.id} />
        {items.length > 0 ? (
          <p className="mt-1.5 text-meta text-muted tabular-nums">{t('caseActions.openCount', { open: workflow.openActionCount, total: actions.data.total })}</p>
        ) : null}
        {canWork ? <AddActionRow changeId={change.id} caseVersion={workflow.version} ownerName={workflow.owner?.name ?? null} /> : null}
      </>
    );
  }

  return (
    <Panel title={t('caseActions.heading')} data-case-panel="actions">
      {workflow.category === 'signoff' ? <Notice data-actions-locked="">{t('caseActions.locked')}</Notice> : null}
      {body}
      <Modal
        open={removing !== null}
        onOpenChange={(open) => (open ? undefined : setRemoving(null))}
        title={t('caseActions.removeTitle', { title: removing?.title ?? '' })}
        description={t('caseActions.removeBody')}
      >
        <ButtonBar>
          <Button variant="outline" onClick={() => setRemoving(null)}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" disabled={remove.isPending} onClick={confirmRemove}>
            {t('caseActions.remove')}
          </Button>
        </ButtonBar>
      </Modal>
    </Panel>
  );
}
