'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { isStaleWrite, useRegisterEntry, useReloadRegister, useSetApplicability, useSpannedEntities } from '@/features/register/hooks';
import { presentApplicability } from '@/features/register/register-presentation';
import type { Applicability, RegisterEntry } from '@/features/register/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';

// "Does it apply to us?": the answer per legal entity where the obligation spans
// several, else for the obligation as a whole, each with its reason and who set
// it when (REG-01, D-42). One person holding applicability.approve answers, then
// confirms in a second step; the answer is stored at once with no second person
// and no passkey (D-75). Cancelling either step stores nothing. The compliance
// status is never read or written here: "applies" and "we comply" are separate.

const APPROVE_PERMISSION = 'applicability.approve';
const ANSWERS: readonly Applicability[] = ['applies', 'not_applicable', 'under_assessment'];
// The server's limit on a reason (apps/register/schemas.py REASON_MAX).
const REASON_MAX = 2000;

/** One answer the panel shows: the whole obligation (`orgUnitId` null) or one legal entity. */
interface Answer {
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

export function ObligationApplicabilityPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const canDecide = (usePermissions() ?? []).includes(APPROVE_PERMISSION);
  const entry = useRegisterEntry(obligationId);
  const span = useSpannedEntities(obligationId);
  const [open, setOpen] = useState<Answer | null>(null);
  const [saved, setSaved] = useState<Applicability | null>(null);

  if (entry.isError || span.isError) {
    return (
      <Panel title={t('obligationApplicability.heading')} data-applicability-panel="">
        <ErrorState
          title={t('obligationApplicability.errorTitle')}
          onRetry={() => {
            void entry.refetch();
            void span.refetch();
          }}
        />
      </Panel>
    );
  }
  if (entry.data === undefined || span.data === undefined) return <LoadingState rows={1} />;

  const answers = answersOf(entry.data, span.data);
  const perEntity = answers.some((answer) => answer.orgUnitId !== null);
  const rows = answers.map((answer) => {
    const body = (
      <>
        {answer.orgUnitId === null && !perEntity ? null : <h3>{answer.name ?? t('obligationApplicability.whole')}</h3>}
        <Meta>
          <PillRow pills={[presentApplicability(answer.applicability, t)]} />
          {answer.decidedBy !== null && answer.decidedAt !== null ? (
            <span>{t('obligationApplicability.decidedBy', { name: answer.decidedBy, date: formatDate(answer.decidedAt, ctx) })}</span>
          ) : null}
        </Meta>
        <p className="mt-1.5">{answer.reason ?? t('obligationApplicability.notDecided')}</p>
        {canDecide ? (
          <ButtonBar className="mt-2 justify-start">
            <Button
              variant={answer.applicability === 'under_assessment' ? 'primary' : 'ghost'}
              size="small"
              onClick={() => {
                setSaved(null);
                setOpen(answer);
              }}
            >
              {answer.applicability === 'under_assessment' ? t('obligationApplicability.decide') : t('obligationApplicability.change')}
            </Button>
          </ButtonBar>
        ) : null}
      </>
    );
    const key = answer.orgUnitId ?? 'whole';
    return perEntity ? (
      <Row key={key} data-applicability-row={key}>
        {body}
      </Row>
    ) : (
      <div key={key} data-applicability-row={key}>
        {body}
      </div>
    );
  });

  return (
    <Panel title={t('obligationApplicability.heading')} data-applicability-panel="">
      {perEntity ? <Rows>{rows}</Rows> : rows}
      {saved === null ? null : <StatusLine tone="positive">{t('obligationApplicability.saved', { value: presentApplicability(saved, t).label })}</StatusLine>}
      <p className="mt-2.5 text-meta text-muted">{t('obligationApplicability.separateFacts')}</p>
      {open === null ? null : (
        <DecideDialog
          obligationId={obligationId}
          answer={open}
          onClose={(stored) => {
            setOpen(null);
            if (stored !== null) setSaved(stored);
          }}
        />
      )}
    </Panel>
  );
}

/** Answer, then confirm: nothing is sent before the second step's button. */
function DecideDialog({ obligationId, answer, onClose }: { obligationId: string; answer: Answer; onClose: (stored: Applicability | null) => void }) {
  const t = useT();
  const set = useSetApplicability(obligationId);
  const reload = useReloadRegister();
  const [value, setValue] = useState<Applicability>(answer.applicability === 'under_assessment' ? 'applies' : answer.applicability);
  const [reason, setReason] = useState(answer.reason ?? '');
  const [confirming, setConfirming] = useState(false);
  const entity = answer.name ?? t('obligationApplicability.whole');
  const label = presentApplicability(value, t).label;

  const next = (event: FormEvent) => {
    event.preventDefault();
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
            {t('obligationApplicability.reload')}
          </Button>
        </ButtonBar>
      </div>
    ) : (
      <ProblemAlert error={set.error} />
    )
  ) : null;

  if (confirming) {
    return (
      <Modal
        open
        onOpenChange={(stay) => (stay ? undefined : onClose(null))}
        title={answer.orgUnitId === null ? t('obligationApplicability.confirmTitleWhole', { value: label }) : t('obligationApplicability.confirmTitle', { value: label, entity })}
        description={t('obligationApplicability.confirmBody', { before: presentApplicability(answer.applicability, t).label })}
      >
        {problem}
        <ButtonBar>
          <Button variant="outline" onClick={() => onClose(null)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={store} disabled={set.isPending}>
            {t('obligationApplicability.confirm')}
          </Button>
        </ButtonBar>
      </Modal>
    );
  }

  return (
    <Modal
      open
      onOpenChange={(stay) => (stay ? undefined : onClose(null))}
      title={answer.orgUnitId === null ? t('obligationApplicability.heading') : t('obligationApplicability.formTitle', { entity })}
    >
      <form onSubmit={next} noValidate>
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
        <ButtonBar>
          <Button variant="outline" onClick={() => onClose(null)}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={reason.trim() === ''}>
            {t('obligationApplicability.continue')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}
