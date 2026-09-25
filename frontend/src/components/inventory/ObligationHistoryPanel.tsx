'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { isStaleWrite, useAssessments, useInterpretation, useReloadRegister, useSaveInterpretation } from '@/features/register/hooks';
import { presentCompliance } from '@/features/register/register-presentation';
import type { RegisterAssessmentPage, RegisterInterpretation } from '@/features/register/types';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';

// "How we read this rule" and the assessment history (REG-04;
// design/screens/tenant-obligation.html). A reading is a version with its
// author and date and no approval step: a member holding register.edit writes
// the next one under If-Match, and every earlier one stays readable. The
// history beneath it is append-only, newest first, a page at a time, and
// nothing on it is ever edited.

const EDIT_PERMISSION = 'register.edit';
export const HISTORY_PAGE = 20;

type Assessment = RegisterAssessmentPage['items'][number];
type ReadingVersion = NonNullable<RegisterInterpretation['current']>;

const METHOD_LABEL: Record<Assessment['method'], MessageKey> = {
  self_assessment: 'obligationHistory.method.selfAssessment',
  second_line_review: 'obligationHistory.method.secondLineReview',
  internal_audit: 'obligationHistory.method.internalAudit',
  external_audit: 'obligationHistory.method.externalAudit',
  regulator: 'obligationHistory.method.regulator',
};

function ReadingEditor({ obligationId, current, onOpenChange }: { obligationId: string; current: ReadingVersion | null; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const [text, setText] = useState(current?.text ?? '');
  const save = useSaveInterpretation(obligationId);
  const reload = useReloadRegister();
  const version = current?.versionNo ?? 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate({ body: { text: text.trim() }, version }, { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Modal open onOpenChange={onOpenChange} title={t('obligationHistory.heading')}>
      <form onSubmit={submit} noValidate aria-busy={save.isPending} data-reading-editor="">
        <Field id="reading-text" label={t('obligationHistory.editorLabel')} hint={t('obligationHistory.editorHint', { version: version + 1 })}>
          <TextArea id="reading-text" className="min-h-[120px]" value={text} onChange={(event) => setText(event.target.value)} />
        </Field>
        {save.isError ? <ProblemAlert error={save.error} codes={{ stale_write: t('obligationHistory.stale') }} /> : null}
        <ButtonBar>
          {isStaleWrite(save.error) ? (
            <Button variant="outline" onClick={() => void reload().then(() => onOpenChange(false))}>
              {t('obligationHistory.reload')}
            </Button>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
          )}
          <Button type="submit" disabled={text.trim() === '' || save.isPending || isStaleWrite(save.error)}>
            {t('obligationHistory.save')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function ReadingLine({ reading }: { reading: ReadingVersion }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <p className="mt-1.5 text-meta text-muted" data-reading-by="">
      {t('obligationHistory.readingBy', { version: reading.versionNo, name: reading.author.name, date: formatDate(reading.writtenAt, ctx) })}
    </p>
  );
}

function Reading({ obligationId, canEdit }: { obligationId: string; canEdit: boolean }) {
  const t = useT();
  const reading = useInterpretation(obligationId);
  const [editing, setEditing] = useState(false);
  const [showEarlier, setShowEarlier] = useState(false);

  if (reading.isPending) return <LoadingState rows={1} />;
  if (reading.isError) return <ErrorState title={t('obligationHistory.readingError')} onRetry={() => void reading.refetch()} />;
  const { current, earlier } = reading.data;
  return (
    <div data-reading="">
      {current === null ? (
        <p className="text-meta text-muted" data-reading-empty="">
          {t('obligationHistory.readingEmpty')}
        </p>
      ) : (
        <div data-reading-current={current.versionNo}>
          <p className="whitespace-pre-line">{current.text}</p>
          <ReadingLine reading={current} />
        </div>
      )}
      {canEdit ? (
        <ButtonBar className="justify-start">
          <Button variant="outline" size="small" onClick={() => setEditing(true)}>
            {t(current === null ? 'obligationHistory.writeFirst' : 'obligationHistory.writeNew')}
          </Button>
        </ButtonBar>
      ) : null}
      {earlier.length === 0 ? null : (
        <div className="mt-2">
          <Button variant="ghost" size="small" aria-expanded={showEarlier} onClick={() => setShowEarlier(!showEarlier)}>
            {t('obligationHistory.earlier', { count: earlier.length })}
          </Button>
          {showEarlier ? (
            <div className="mt-2 grid gap-2.5" data-reading-earlier="">
              {earlier.map((row) => (
                <div key={row.versionNo} className="border-l-2 border-line pl-3" data-reading-version={row.versionNo}>
                  <p className="whitespace-pre-line text-muted">{row.text}</p>
                  <ReadingLine reading={row} />
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
      {editing ? <ReadingEditor obligationId={obligationId} current={current} onOpenChange={setEditing} /> : null}
    </div>
  );
}

function AssessmentRow({ assessment }: { assessment: Assessment }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <div className="border-b border-line py-2.5 last:border-b-0" data-assessment-id={assessment.id}>
      <Meta>
        <PillRow pills={[presentCompliance(assessment.status)]} />
        <span>{formatDate(assessment.assessedAt, ctx)}</span>
        <span>{assessment.assessedBy.name}</span>
        <span>{t(METHOD_LABEL[assessment.method])}</span>
        {assessment.orgUnitName === null ? null : <span>{assessment.orgUnitName}</span>}
      </Meta>
      {assessment.rationale === '' ? null : <p className="mt-1 whitespace-pre-line">{assessment.rationale}</p>}
    </div>
  );
}

function History({ obligationId }: { obligationId: string }) {
  const t = useT();
  const [offset, setOffset] = useState(0);
  const history = useAssessments(obligationId, { limit: HISTORY_PAGE, offset });

  if (history.isPending) return <LoadingState rows={1} />;
  if (history.isError) return <ErrorState title={t('obligationHistory.historyError')} onRetry={() => void history.refetch()} />;
  const { items, total } = history.data;
  if (items.length === 0) {
    return (
      <p className="text-meta text-muted" data-history-empty="">
        {t('obligationHistory.historyEmpty')}
      </p>
    );
  }
  return (
    <>
      <div data-history="">
        {items.map((assessment) => (
          <AssessmentRow key={assessment.id} assessment={assessment} />
        ))}
      </div>
      {total > HISTORY_PAGE ? (
        <ButtonBar className="justify-between">
          <Button variant="ghost" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - HISTORY_PAGE))}>
            {t('obligationHistory.newer')}
          </Button>
          <Meta>{t('obligationHistory.range', { from: offset + 1, to: offset + items.length, total })}</Meta>
          <Button variant="ghost" size="small" disabled={offset + items.length >= total} onClick={() => setOffset(offset + HISTORY_PAGE)}>
            {t('obligationHistory.older')}
          </Button>
        </ButtonBar>
      ) : null}
    </>
  );
}

export function ObligationHistoryPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const canEdit = (usePermissions() ?? []).includes(EDIT_PERMISSION);
  return (
    <Panel title={t('obligationHistory.heading')} data-history-panel="">
      <Reading obligationId={obligationId} canEdit={canEdit} />
      <h3 className="mt-4 mb-2">{t('obligationHistory.historyTitle')}</h3>
      <History obligationId={obligationId} />
    </Panel>
  );
}
