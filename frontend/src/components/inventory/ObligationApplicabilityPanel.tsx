'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea } from '@/components/ui/Field';
import { ProblemAlert } from '@/components/ui/States';
import { ConfirmDialog, FormDialog } from '@/components/ui/Dialogs';
import { isStaleWrite, useReloadRegister, useSetApplicability } from '@/features/register/hooks';
import { presentApplicability } from '@/features/register/register-presentation';
import type { Applicability, RegisterEntry } from '@/features/register/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Does it apply?": the answer per legal entity where the obligation spans
// several, else for the obligation as a whole, each with its reason and who set
// it when (REG-01, D-42). The answers are drawn per company in "Our position"
// (ObligationPositionPanel); this file holds which answers there are and the
// dialog that sets one. One person holding applicability.approve answers, then
// confirms in a second step; the answer is stored at once with no second person
// and no passkey (D-75). Cancelling either step stores nothing. The compliance
// status is never read or written here: "applies" and "we comply" are separate.

export const APPROVE_PERMISSION = 'applicability.approve';
const ANSWERS: readonly Applicability[] = ['applies', 'not_applicable', 'under_assessment'];
// The server's limit on a reason (apps/register/schemas.py REASON_MAX).
const REASON_MAX = 2000;

/** One answer the page shows: the whole obligation (`orgUnitId` null) or one legal entity. */
export interface Answer {
  orgUnitId: string | null;
  name: string | null;
  applicability: Applicability;
  reason: string | null;
  decidedAt: string | null;
  decidedBy: string | null;
  version: number;
}

/**
 * Every entity the obligation spans, answered or not, then any entity row the
 * bank holds outside today's span; per entity only where there are several.
 * The whole obligation's own answer stays on show once someone gave it.
 */
export function answersOf(entry: RegisterEntry, spanned: readonly { orgUnitId: string; orgUnitName: string }[]): Answer[] {
  const rows = new Map(entry.entities.map((row) => [row.orgUnitId, row]));
  const outside = entry.entities.filter((row) => !spanned.some((entity) => entity.orgUnitId === row.orgUnitId));
  const named = [...spanned, ...outside.map((row) => ({ orgUnitId: row.orgUnitId, orgUnitName: row.orgUnitName }))];
  const entities: Answer[] = named.map(({ orgUnitId, orgUnitName }) => {
    const row = rows.get(orgUnitId);
    return {
      orgUnitId,
      name: orgUnitName,
      applicability: row?.applicability ?? 'under_assessment',
      reason: row?.applicabilityReason ?? null,
      decidedAt: row?.applicabilityDecidedAt ?? null,
      decidedBy: row?.applicabilityDecidedBy?.name ?? null,
      version: row?.version ?? 0,
    };
  });
  const whole: Answer = {
    orgUnitId: null,
    name: null,
    applicability: entry.applicability,
    reason: entry.applicabilityReason,
    decidedAt: entry.applicabilityDecidedAt,
    decidedBy: entry.applicabilityDecidedBy?.name ?? null,
    version: entry.version,
  };
  if (entities.length < 2) return [whole];
  return entry.applicability === 'under_assessment' ? entities : [whole, ...entities];
}

/** Answer, then confirm: nothing is sent before the second step's button. */
export function DecideDialog({ obligationId, answer, onClose }: { obligationId: string; answer: Answer; onClose: (stored: Applicability | null) => void }) {
  const t = useT();
  const set = useSetApplicability(obligationId);
  const reload = useReloadRegister();
  const [value, setValue] = useState<Applicability>(answer.applicability === 'under_assessment' ? 'applies' : answer.applicability);
  const [reason, setReason] = useState(answer.reason ?? '');
  const [confirming, setConfirming] = useState(false);
  const entity = answer.name ?? t('obligationApplicability.whole');
  const label = presentApplicability(value, t).label;

  const next = () => {
    setConfirming(true);
  };
  const store = () =>
    set.mutate(
      { body: { applicability: value, reason: reason.trim(), ...(answer.orgUnitId === null ? {} : { orgUnitId: answer.orgUnitId }) }, version: answer.version },
      { onSuccess: () => onClose(value) },
    );

  const problem = set.isError ? (
    isStaleWrite(set.error) ? (
      <div role="alert" className="mt-2.5 text-meta text-negative" data-stale-write="">
        {t('obligationApplicability.stale')}
        <ButtonBar className="mt-2 justify-start">
          <Button
            variant="outline"
            size="small"
            onClick={() => {
              void reload();
              onClose(null);
            }}
          >
            {t('common.reload')}
          </Button>
        </ButtonBar>
      </div>
    ) : (
      <ProblemAlert error={set.error} />
    )
  ) : null;

  if (confirming) {
    return (
      <ConfirmDialog
        title={answer.orgUnitId === null ? t('obligationApplicability.confirmTitleWhole', { value: label }) : t('obligationApplicability.confirmTitle', { value: label, entity })}
        body={t('obligationApplicability.confirmBody', { before: presentApplicability(answer.applicability, t).label })}
        action={t('obligationApplicability.confirm')}
        busy={set.isPending}
        onConfirm={store}
        onClose={() => onClose(null)}
      >
        {problem}
      </ConfirmDialog>
    );
  }

  return (
    <FormDialog
      title={answer.orgUnitId === null ? t('obligationApplicability.heading') : t('obligationApplicability.formTitle', { entity })}
      submitLabel={t('obligationApplicability.continue')}
      pending={false}
      submitDisabled={reason.trim() === ''}
      onSubmit={next}
      onClose={() => onClose(null)}
    >
      <Field id="applicability-value" label={t('obligationApplicability.decision')}>
        <Select id="applicability-value" value={value} onChange={(event) => setValue(event.target.value as Applicability)}>
          {ANSWERS.map((option) => (
            <option key={option} value={option}>
              {presentApplicability(option, t).label}
            </option>
          ))}
        </Select>
      </Field>
      <Field id="applicability-reason" label={t('obligationApplicability.reason')} hint={t('obligationApplicability.reasonHint')}>
        <TextArea id="applicability-reason" value={reason} maxLength={REASON_MAX} onChange={(event) => setReason(event.target.value)} />
      </Field>
    </FormDialog>
  );
}
