'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel } from '@/components/ui/Panel';
import { CASES_CONTRIBUTE, refusedFieldsOf, useSaveAssessment } from '@/features/cases/hooks';
import type { AssessmentBody, CaseAssessment, CasePanelProps, CaseWorkflow } from '@/features/cases/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { CASES_WORK } from '@/features/watch/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, formatDateTime } from '@/shared/utils/format';

import { Refusal } from './TriagePanel';

// The impact assessment (design/screens/tenant-change.html, case panels
// part A; CAS-03, CAS-08, D-92): whether the change applies, why, what must
// change, the bank's own deadline, the effort and the case's status inside
// its category. Contributor teams are the participants panel's.
//
// A holder of `cases.contribute` edits it while the case is assessed or
// implemented; everyone else, and everyone from waiting for sign-off on,
// reads it, and a reader sends no request. "No" closes the case on one
// person's word, so it is offered only to a holder of `cases.work`, only
// while assessing, and asks before it saves. The save carries the case's
// version: a save somebody else's overtook is refused, the person's text
// stays on screen, and a reload is offered, never a merge.

type Applies = AssessmentBody['applies'];

const EDITABLE: ReadonlySet<CaseWorkflow['category']> = new Set(['assessing', 'implementing']);

const APPLIES_KEY = {
  yes: 'caseAssessment.applies.yes',
  partly: 'caseAssessment.applies.partly',
  no: 'caseAssessment.applies.no',
} as const satisfies Record<Applies, MessageKey>;

export function AssessmentPanel({ change, workflow }: CasePanelProps) {
  const assessment = workflow.assessment ?? null;
  // A case closed before its assessment started has nothing to show here.
  if (assessment === null && !EDITABLE.has(workflow.category)) return null;
  return <Assessment changeId={change.id} workflow={workflow} assessment={assessment} />;
}

function Assessment({ changeId, workflow, assessment }: { changeId: string; workflow: CaseWorkflow; assessment: CaseAssessment | null }) {
  const permissions = usePermissions() ?? [];
  // Bumped once a reload after a stale write has landed, so the form starts
  // again from the version now on screen.
  const [generation, setGeneration] = useState(0);
  if (!permissions.includes(CASES_CONTRIBUTE) || !EDITABLE.has(workflow.category)) {
    return assessment === null ? null : <AssessmentRead assessment={assessment} />;
  }
  return (
    <AssessmentForm
      key={generation}
      changeId={changeId}
      workflow={workflow}
      assessment={assessment}
      canClose={permissions.includes(CASES_WORK) && workflow.category === 'assessing'}
      onReloaded={() => setGeneration((value) => value + 1)}
    />
  );
}

// ---------------------------------------------------------------------------
// Read-only
// ---------------------------------------------------------------------------

function AssessmentRead({ assessment }: { assessment: CaseAssessment }) {
  const t = useT();
  const ctx = useFormatContext();
  const rows: [string, string | null][] = [
    [t('caseAssessment.appliesTerm'), t(APPLIES_KEY[assessment.applies])],
    [t('caseAssessment.why'), assessment.why],
    [t('caseAssessment.whatMustChange'), assessment.whatMustChange],
    [t('caseAssessment.deadline'), assessment.internalDeadline === null ? null : formatDate(assessment.internalDeadline, ctx)],
    [t('caseAssessment.effort'), assessment.effort?.label ?? null],
    [t('caseAssessment.savedTerm'), savedLine(assessment, t, ctx)],
  ];
  return (
    <Panel title={t('caseAssessment.heading')} data-case-panel="assessment" data-read-only="">
      <dl className="grid gap-x-4 gap-y-1 md:grid-cols-[auto_1fr]">
        {rows
          .filter((row): row is [string, string] => row[1] !== null)
          .map(([term, value]) => (
            <div key={term} className="contents">
              <dt className="text-muted">{term}</dt>
              <dd className="m-0 mb-2 whitespace-pre-line">{value}</dd>
            </div>
          ))}
      </dl>
    </Panel>
  );
}

function savedLine(assessment: CaseAssessment, t: ReturnType<typeof useT>, ctx: ReturnType<typeof useFormatContext>): string {
  if (!assessment.saved || assessment.savedBy === null || assessment.savedAt === null) return t('caseAssessment.notSaved');
  return t('caseAssessment.savedLine', { version: assessment.version, name: assessment.savedBy.name, date: formatDateTime(assessment.savedAt, ctx) });
}

// ---------------------------------------------------------------------------
// The form
// ---------------------------------------------------------------------------

function AssessmentForm({
  changeId,
  workflow,
  assessment,
  canClose,
  onReloaded,
}: {
  changeId: string;
  workflow: CaseWorkflow;
  assessment: CaseAssessment | null;
  canClose: boolean;
  onReloaded: () => void;
}) {
  const t = useT();
  const ctx = useFormatContext();
  const efforts = useVocabularyValues('effort_size');
  const subStatuses = useVocabularyValues('case_sub_status');
  const save = useSaveAssessment(changeId, workflow.version);
  const [applies, setApplies] = useState<Applies>(assessment?.applies ?? 'yes');
  const [why, setWhy] = useState(assessment?.why ?? '');
  const [whatMustChange, setWhatMustChange] = useState(assessment?.whatMustChange ?? '');
  const [deadline, setDeadline] = useState(assessment?.internalDeadline ?? '');
  const [effort, setEffort] = useState(assessment?.effort?.key ?? '');
  const [subStatus, setSubStatus] = useState(workflow.subStatus?.key ?? '');
  const [confirmingClose, setConfirmingClose] = useState(false);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);
  const refused = refusedFieldsOf(save.error);
  const invalid = (field: string) => refused.includes(field) || undefined;
  const offered: Applies[] = canClose ? ['yes', 'partly', 'no'] : ['yes', 'partly'];

  const send = () => {
    setConfirmingClose(false);
    setSavedVersion(null);
    save.mutate(
      {
        applies,
        why: why.trim(),
        whatMustChange: whatMustChange.trim(),
        internalDeadline: deadline === '' ? null : deadline,
        effort: effort === '' ? null : effort,
        // "No" moves the case to closed, where this category's status does not sit.
        subStatus: applies === 'no' || subStatus === '' ? null : subStatus,
      },
      { onSuccess: (saved) => setSavedVersion(saved.assessment?.version ?? null) },
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (applies === 'no') setConfirmingClose(true);
    else send();
  };

  return (
    <Panel title={t('caseAssessment.heading')} data-case-panel="assessment">
      <form onSubmit={submit} noValidate aria-busy={save.isPending}>
        {assessment !== null ? (
          <Meta className="mb-3.5">
            <span>{t('caseAssessment.version', { version: assessment.version })}</span>
            <span>
              {assessment.saved && assessment.savedBy !== null && assessment.savedAt !== null
                ? t('caseAssessment.savedBy', { name: assessment.savedBy.name, date: formatDateTime(assessment.savedAt, ctx) })
                : t('caseAssessment.notSaved')}
            </span>
          </Meta>
        ) : null}
        <fieldset className="mb-3.5 grid gap-0 rounded-control border border-line px-3.5 py-0.5" aria-describedby={canClose ? undefined : 'assessment-no-hint'}>
          <legend className="px-1 font-medium">{t('caseAssessment.applies')}</legend>
          {offered.map((value) => (
            <label key={value} className="flex items-start gap-2.5 border-b border-line py-2 last:border-b-0">
              <input type="radio" name="assessment-applies" className="mt-1 size-4 accent-button" value={value} checked={applies === value} onChange={() => setApplies(value)} />
              <span>
                {t(APPLIES_KEY[value])}
                {value === 'no' ? <small className="block text-meta text-muted">{t('caseAssessment.noHint')}</small> : null}
              </span>
            </label>
          ))}
          {canClose || workflow.category !== 'assessing' ? null : (
            <span id="assessment-no-hint" className="py-2 text-meta text-muted">
              {t('caseAssessment.noOwnerOnly')}
            </span>
          )}
        </fieldset>
        <Field id="assessment-why" label={t('caseAssessment.why')} error={invalid('why') ? t('caseAssessment.whyRequired') : undefined}>
          <TextArea
            id="assessment-why"
            value={why}
            aria-invalid={invalid('why')}
            aria-describedby={invalid('why') ? 'assessment-why-error' : undefined}
            onChange={(event) => setWhy(event.target.value)}
          />
        </Field>
        <Field id="assessment-change" label={t('caseAssessment.whatMustChange')} error={invalid('whatMustChange') ? t('caseAssessment.fieldInvalid') : undefined}>
          <TextArea
            id="assessment-change"
            value={whatMustChange}
            placeholder={t('caseAssessment.whatMustChangePlaceholder')}
            aria-invalid={invalid('whatMustChange')}
            onChange={(event) => setWhatMustChange(event.target.value)}
          />
        </Field>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="assessment-deadline" label={t('caseAssessment.deadline')} error={invalid('internalDeadline') ? t('caseAssessment.fieldInvalid') : undefined}>
            <TextInput id="assessment-deadline" type="date" value={deadline} aria-invalid={invalid('internalDeadline')} onChange={(event) => setDeadline(event.target.value)} />
          </Field>
          <Field id="assessment-effort" label={t('caseAssessment.effort')} error={invalid('effort') ? t('caseAssessment.fieldInvalid') : undefined}>
            <Select id="assessment-effort" value={effort} aria-invalid={invalid('effort')} onChange={(event) => setEffort(event.target.value)}>
              <option value="">{t('caseAssessment.effortNone')}</option>
              {(efforts.data ?? [])
                .filter((row) => row.active !== false || row.key === effort)
                .map((row) => (
                  <option key={row.key} value={row.key}>
                    {row.label}
                  </option>
                ))}
            </Select>
          </Field>
        </div>
        <Field id="assessment-status" label={t('caseAssessment.status')} hint={t('caseAssessment.statusHint')} error={invalid('subStatus') ? t('caseAssessment.fieldInvalid') : undefined}>
          <Select
            id="assessment-status"
            value={subStatus}
            aria-invalid={invalid('subStatus')}
            aria-describedby="assessment-status-hint"
            onChange={(event) => setSubStatus(event.target.value)}
          >
            <option value="">{t('caseAssessment.statusNone')}</option>
            {/* A status sits inside one category; the case's own is the only one it can carry here. */}
            {(subStatuses.data ?? [])
              .filter((row) => row.kind === workflow.category && (row.active !== false || row.key === subStatus))
              .map((row) => (
                <option key={row.key} value={row.key}>
                  {row.label}
                </option>
              ))}
          </Select>
        </Field>
        <Refusal error={save.error} changeId={changeId} handled={refused.length > 0} onReloaded={onReloaded} />
        {savedVersion !== null && save.isSuccess ? (
          <p role="status" className="mt-2.5 text-meta text-positive">
            {t('caseAssessment.saved', { version: savedVersion })}
          </p>
        ) : null}
        <ButtonBar>
          <Button type="submit" disabled={save.isPending}>
            {t('caseAssessment.save')}
          </Button>
        </ButtonBar>
      </form>
      <Modal open={confirmingClose} onOpenChange={setConfirmingClose} title={t('caseAssessment.closeTitle')} description={t('caseAssessment.closeBody')}>
        <ButtonBar>
          <Button variant="ghost" onClick={() => setConfirmingClose(false)}>
            {t('caseAssessment.keepEditing')}
          </Button>
          <Button disabled={save.isPending} onClick={send}>
            {t('caseAssessment.saveAndClose')}
          </Button>
        </ButtonBar>
      </Modal>
    </Panel>
  );
}
