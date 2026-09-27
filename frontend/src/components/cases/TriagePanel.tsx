'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { ProblemAlert } from '@/components/ui/States';
import { closeKindOf } from '@/features/cases/case-presentation';
import {
  CASES_TRIAGE,
  refusedFieldsOf,
  staleWriteOf,
  useCaseWorkers,
  useCloseWithoutAction,
  useDismissChange,
  useReloadCase,
  useRestoreChange,
  useStartAssessment,
  useTriageChange,
} from '@/features/cases/hooks';
import type { CasePanelProps, CaseWorkflow } from '@/features/cases/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import type { VocabularyRow } from '@/features/vocabularies/types';
import { CASES_WORK } from '@/features/watch/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// Triage, the next step, the one-person close and Move back to triage
// (design/screens/tenant-change.html, case panels part A and the closed and
// dismissed states of part B; CAS-02, CAS-08, D-92). The change page mounts
// this panel for a case that needs triage, is assigned or assessing, was
// dismissed, or was closed by one person (CaseWorkPanels).
//
// A control shows only when the case's `allowedTransitions` holds its move
// and the reader holds the move's permission, so nobody is offered a button
// that could answer 403, and a reader without it sends no request at all:
// not even the lists a form would need. Urgency, the optional owning team
// and reasons go as keys, the owner as an id; every label is the bank's own row. A refusal renders where it was
// made, from the server's answer: a 422 under the field its `errors` names,
// `stale_write` as a reload offer that leaves the person's choice alone.

export function TriagePanel({ change, workflow }: CasePanelProps) {
  switch (workflow.category) {
    case 'new':
      return <NeedsTriage agent={change.model} changeId={change.id} workflow={workflow} />;
    case 'assigned':
    case 'assessing':
      return <NextStep changeId={change.id} workflow={workflow} />;
    case 'dismissed':
    case 'closed':
      return <Decided changeId={change.id} workflow={workflow} />;
    default:
      return null;
  }
}

function useHolds(permission: string): boolean {
  return (usePermissions() ?? []).includes(permission);
}

// ---------------------------------------------------------------------------
// Needs triage
// ---------------------------------------------------------------------------

function NeedsTriage({ changeId, workflow, agent }: { changeId: string; workflow: CaseWorkflow; agent: string | null }) {
  const t = useT();
  const canTriage = useHolds(CASES_TRIAGE);
  if (!canTriage) {
    return (
      <Panel title={t('caseTriage.heading')} data-case-panel="triage">
        <p className="m-0">{t('caseTriage.readOnly')}</p>
      </Panel>
    );
  }
  return <TriageForm changeId={changeId} workflow={workflow} agent={agent} />;
}

function TriageForm({ changeId, workflow, agent }: { changeId: string; workflow: CaseWorkflow; agent: string | null }) {
  const t = useT();
  const people = useCaseWorkers();
  const urgencies = useVocabularyValues('urgency');
  const teams = useVocabularyValues('team');
  const triage = useTriageChange(changeId, workflow.version);
  const [urgency, setUrgency] = useState(workflow.urgency?.key ?? '');
  const [ownerId, setOwnerId] = useState(workflow.ownerId ?? '');
  const [ownerTeam, setOwnerTeam] = useState('');
  const [dismissing, setDismissing] = useState(false);
  const canAssign = workflow.allowedTransitions.includes('assigned');
  const canDismiss = workflow.allowedTransitions.includes('dismissed');
  const refused = refusedFieldsOf(triage.error);
  const ownerRefused = refused.includes('ownerId') || hasProblemCode(triage.error, 'owner_required');
  const teamRefused = refused.includes('ownerTeam');
  const suggested = workflow.urgency !== null && !workflow.urgencyConfirmed;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    triage.mutate({ urgency, ownerId, ...(ownerTeam === '' ? {} : { ownerTeam }) });
  };

  return (
    <Panel title={t('caseTriage.heading')} data-case-panel="triage">
      <form onSubmit={submit} noValidate aria-busy={triage.isPending}>
        <p className="text-muted">{t('caseTriage.intro')}</p>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field
            id="triage-urgency"
            label={t('caseTriage.urgency')}
            hint={!suggested ? undefined : agent === null ? t('caseTriage.urgencySuggested') : t('caseTriage.urgencySuggestedBy', { agent })}
            error={refused.includes('urgency') ? t('caseTriage.fieldInvalid') : undefined}
          >
            <Select id="triage-urgency" value={urgency} aria-invalid={refused.includes('urgency') || undefined} onChange={(event) => setUrgency(event.target.value)}>
              <option value="">{t('caseTriage.urgencyChoose')}</option>
              {(urgencies.data ?? []).filter(isOffered).map((row) => (
                <option key={row.key} value={row.key}>
                  {row.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="triage-owner" label={t('caseTriage.owner')} hint={t('caseTriage.ownerHint')} error={ownerRefused ? t('caseTriage.ownerRequired') : undefined}>
            <Select
              id="triage-owner"
              value={ownerId}
              aria-invalid={ownerRefused || undefined}
              aria-describedby={ownerRefused ? 'triage-owner-error' : 'triage-owner-hint'}
              onChange={(event) => setOwnerId(event.target.value)}
            >
              <option value="">{t('caseTriage.ownerChoose')}</option>
              {(people.data ?? []).map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="triage-team" label={t('caseTriage.team')} error={teamRefused ? t('caseTriage.fieldInvalid') : undefined}>
            <Select
              id="triage-team"
              value={ownerTeam}
              aria-invalid={teamRefused || undefined}
              aria-describedby={teamRefused ? 'triage-team-error' : undefined}
              onChange={(event) => setOwnerTeam(event.target.value)}
            >
              <option value="">{t('caseTriage.teamNone')}</option>
              {(teams.data ?? []).filter(isOffered).map((row) => (
                <option key={row.key} value={row.key}>
                  {row.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Refusal error={triage.error} changeId={changeId} handled={hasProblemCode(triage.error, 'owner_required') || shownAll(refused, ['urgency', 'ownerId', 'ownerTeam'])} />
        <ButtonBar>
          {canDismiss ? (
            <Button variant="danger" disabled={triage.isPending} onClick={() => setDismissing(true)}>
              {t('caseTriage.dismiss')}
            </Button>
          ) : null}
          {canAssign ? (
            <Button type="submit" disabled={triage.isPending}>
              {t('caseTriage.confirm')}
            </Button>
          ) : null}
        </ButtonBar>
      </form>
      {dismissing ? <DismissDialog changeId={changeId} version={workflow.version} onClose={() => setDismissing(false)} /> : null}
    </Panel>
  );
}

function DismissDialog({ changeId, version, onClose }: { changeId: string; version: number; onClose: () => void }) {
  const t = useT();
  const reasons = useVocabularyValues('dismissal_reason');
  const dismiss = useDismissChange(changeId, version);
  const [reasonKey, setReasonKey] = useState('');
  const reasonRefused = refusedFieldsOf(dismiss.error).includes('reasonKey') || hasProblemCode(dismiss.error, 'reason_required');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    dismiss.mutate({ reasonKey }, { onSuccess: onClose });
  };

  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={t('caseTriage.dismissTitle')} description={t('caseTriage.dismissBody')}>
      <form onSubmit={submit} noValidate aria-busy={dismiss.isPending}>
        <ReasonChoice
          name="dismiss-reason"
          rows={reasons.data}
          value={reasonKey}
          onChange={setReasonKey}
          error={reasonRefused ? t('caseTriage.dismissReasonRequired') : undefined}
        />
        <Refusal error={dismiss.error} changeId={changeId} handled={hasProblemCode(dismiss.error, 'reason_required') || shownAll(refusedFieldsOf(dismiss.error), ['reasonKey'])} />
        <ButtonBar>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="danger" disabled={dismiss.isPending}>
            {t('caseTriage.dismiss')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Next step: Start assessment and No action
// ---------------------------------------------------------------------------

function NextStep({ changeId, workflow }: { changeId: string; workflow: CaseWorkflow }) {
  const t = useT();
  const ctx = useFormatContext();
  const canWork = useHolds(CASES_WORK);
  const start = useStartAssessment(changeId, workflow.version);
  const [closing, setClosing] = useState(false);
  const owner = workflow.owner?.name ?? '';
  const date = workflow.triagedAt === null ? '' : formatDate(workflow.triagedAt, ctx);
  const canStart = canWork && workflow.category === 'assigned' && workflow.allowedTransitions.includes('assessing');
  const canClose = canWork && workflow.allowedTransitions.includes('closed');

  return (
    <Panel title={t('caseTriage.nextStep')} data-case-panel="next-step">
      <p className="flex flex-wrap gap-x-1">
        <span>
          {canWork && workflow.triagedBy !== null
            ? t('caseTriage.assignedBy', { owner, by: workflow.triagedBy.name, date })
            : t('caseTriage.assigned', { owner, date })}
        </span>
        {workflow.ownerTeam ? <span>{t('caseTriage.withTeam', { team: workflow.ownerTeam.label })}</span> : null}
        {workflow.category === 'assigned' ? <span>{canWork ? t('caseTriage.nextStepIntro') : t('caseTriage.nextStepReader')}</span> : null}
      </p>
      <Refusal error={start.error} changeId={changeId} handled={false} />
      {canStart || canClose ? (
        <ButtonBar>
          {canClose ? (
            <Button variant="ghost" disabled={start.isPending} onClick={() => setClosing(true)}>
              {t('caseTriage.noAction')}
            </Button>
          ) : null}
          {canStart ? (
            <Button disabled={start.isPending} onClick={() => start.mutate()}>
              {t('caseTriage.startAssessment')}
            </Button>
          ) : null}
        </ButtonBar>
      ) : null}
      {closing ? <NoActionDialog changeId={changeId} version={workflow.version} onClose={() => setClosing(false)} /> : null}
    </Panel>
  );
}

function NoActionDialog({ changeId, version, onClose }: { changeId: string; version: number; onClose: () => void }) {
  const t = useT();
  const reasons = useVocabularyValues('close_reason');
  const close = useCloseWithoutAction(changeId, version);
  const [reasonKey, setReasonKey] = useState('');
  const [note, setNote] = useState('');
  const refused = refusedFieldsOf(close.error);
  const reasonRefused = refused.includes('reasonKey') || hasProblemCode(close.error, 'reason_required');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    close.mutate({ reasonKey, note: note.trim() }, { onSuccess: onClose });
  };

  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={t('caseTriage.noActionTitle')} description={t('caseTriage.noActionBody')}>
      <form onSubmit={submit} noValidate aria-busy={close.isPending}>
        <ReasonChoice
          name="close-reason"
          // The card's No action closes a case that needs no work; "does not
          // apply" is the assessment's own answer, and a sign-off is a second
          // person's, never this dialog's.
          rows={reasons.data?.filter((row) => row.kind === 'no_action')}
          value={reasonKey}
          onChange={setReasonKey}
          error={reasonRefused ? t('caseTriage.closeReasonRequired') : undefined}
        />
        <Field id="close-note" label={t('caseTriage.note')} hint={t('caseTriage.noteHint')} error={refused.includes('note') ? t('caseTriage.fieldInvalid') : undefined}>
          <TextArea
            id="close-note"
            value={note}
            placeholder={t('caseTriage.notePlaceholder')}
            aria-describedby="close-note-hint"
            aria-invalid={refused.includes('note') || undefined}
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>
        <Refusal error={close.error} changeId={changeId} handled={hasProblemCode(close.error, 'reason_required') || shownAll(refused, ['reasonKey', 'note'])} />
        <ButtonBar>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={close.isPending}>
            {t('caseTriage.closeCase')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Dismissed, or closed by one person: the decision and Move back to triage
// ---------------------------------------------------------------------------

function Decided({ changeId, workflow }: { changeId: string; workflow: CaseWorkflow }) {
  const t = useT();
  const ctx = useFormatContext();
  const canTriage = useHolds(CASES_TRIAGE);
  const restore = useRestoreChange(changeId, workflow.version);
  const dismissed = workflow.category === 'dismissed';
  // A signed-off case never comes here (CaseWorkPanels); a close of a kind
  // this screen does not know shows its facts and no way back.
  const notApplicable = !dismissed && closeKindOf(workflow) === 'not_applicable';
  const canRestore = canTriage && workflow.allowedTransitions.includes('new');
  const at = dismissed ? workflow.dismissedAt : workflow.closedAt;
  const date = at === null ? '' : formatDate(at, ctx);
  const why = notApplicable ? workflow.assessment?.why : null;

  return (
    <Panel title={dismissed ? t('caseTriage.dismissedHeading') : t('caseTriage.closedHeading')} data-case-panel={dismissed ? 'dismissed' : 'closed'}>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        {dismissed ? (
          <Term term={t('caseTriage.dismissedBy')}>{t('caseTriage.byOn', { name: workflow.dismissedBy?.name ?? '', date })}</Term>
        ) : (
          <Term term={t('caseTriage.closedOn')}>{date}</Term>
        )}
        <Term term={t('caseTriage.reasonTerm')}>{(dismissed ? workflow.dismissedReason : workflow.closeReason)?.label ?? ''}</Term>
        {!dismissed && workflow.closedNote !== null ? <Term term={t('caseTriage.noteTerm')}>{workflow.closedNote}</Term> : null}
        {why !== null && why !== undefined ? <Term term={t('caseTriage.whyTerm')}>{why}</Term> : null}
      </dl>
      <Refusal error={restore.error} changeId={changeId} handled={false} />
      {canRestore ? (
        <ButtonBar>
          <Button disabled={restore.isPending} onClick={() => restore.mutate()}>
            {t('caseTriage.restore')}
          </Button>
        </ButtonBar>
      ) : null}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Shared pieces
// ---------------------------------------------------------------------------

function Term({ term, children }: { term: string; children: string }) {
  return (
    <>
      <dt className="text-muted">{term}</dt>
      <dd className="m-0">{children}</dd>
    </>
  );
}

/** True when a 422 named fields and every one of them is shown under its own control here. */
export function shownAll(refused: string[], shown: string[]): boolean {
  return refused.length > 0 && refused.every((field) => shown.includes(field));
}

/** Active rows only: a retired reason or urgency is kept on old cases but never offered. */
function isOffered(row: VocabularyRow): boolean {
  return row.active !== false;
}

/** One reason from the bank's own list, each with its usage note as the second line. */
function ReasonChoice({ name, rows, value, onChange, error }: { name: string; rows: VocabularyRow[] | undefined; value: string; onChange: (key: string) => void; error?: string }) {
  const t = useT();
  const offered = (rows ?? []).filter(isOffered);
  return (
    <fieldset className="mb-3 grid gap-0 rounded-control border border-line px-3.5 py-0.5">
      <legend className="px-1 font-medium">{t('caseTriage.reason')}</legend>
      {rows !== undefined && offered.length === 0 ? <p className="my-2 text-meta text-muted">{t('caseTriage.noReasons')}</p> : null}
      {offered.map((row) => (
        <label key={row.key} className="flex items-start gap-2.5 border-b border-line py-2 last:border-b-0">
          <input type="radio" name={name} className="mt-1 size-4 accent-button" value={row.key} checked={value === row.key} onChange={() => onChange(row.key)} />
          <span>
            {row.label}
            {row.usageNote !== '' ? <small className="block text-meta text-muted">{row.usageNote}</small> : null}
          </span>
        </label>
      ))}
      {error !== undefined ? (
        <span role="alert" className="mb-2 text-meta text-negative">
          {error}
        </span>
      ) : null}
    </fieldset>
  );
}

/**
 * A refusal the fields above did not already show: `stale_write` as a
 * reload offer that leaves what the person chose on screen, anything else in
 * the server's own words. `onReloaded` lets a form start again from the
 * version it reloaded, once that version is on screen.
 */
export function Refusal({ error, changeId, handled, onReloaded }: { error: unknown; changeId: string; handled: boolean; onReloaded?: () => void }) {
  const t = useT();
  const reloadCase = useReloadCase(changeId);
  const reload = async () => {
    await reloadCase();
    onReloaded?.();
  };
  if (error === null || error === undefined || handled) return null;
  if (staleWriteOf(error) !== null) {
    return (
      <Notice tone="warn" className="mt-3" data-stale-write="">
        <p className="mb-2">{t('cases.staleWrite.body')}</p>
        <Button size="small" onClick={() => void reload()}>
          {t('cases.staleWrite.reload')}
        </Button>
      </Notice>
    );
  }
  return <ProblemAlert error={error} />;
}
