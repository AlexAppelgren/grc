'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { languageName } from '@/features/library/version-presentation';
import { useCloseProblemReport, useRecordProblemReports } from '@/features/problem-reports/hooks';
import { CLOSE_ANY_PERMISSION, CLOSING_STATUSES, canClose, contextLine, presentProblemReport } from '@/features/problem-reports/problem-report-presentation';
import type { ProblemReport, ProblemReportClosingStatus, ProblemReportSubjectType } from '@/features/problem-reports/types';
import type { MessageKey } from '@/shared/i18n';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// "Reported problems" on a library record (AUD-03, INV-06; D-50): the
// reports this bank filed on it, newest first. A member holding
// `proposals.create` reads and closes every one of them; anyone else reads and
// closes their own, which is what the server answers. A report is the bank's
// own content: it is rendered here and nowhere else, and never logged.

/** Reading the bank's reports is the same permission as filing one. */
const REPORT_PERMISSION = 'problems.report';

const OPTION_LABEL: Record<ProblemReportClosingStatus, MessageKey> = {
  answered: 'inventory.reports.closeOption.answered',
  fixed: 'inventory.reports.closeOption.fixed',
  rejected: 'inventory.reports.closeOption.rejected',
};

function CloseReportModal({ report, onOpenChange }: { report: ProblemReport; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const [status, setStatus] = useState<ProblemReportClosingStatus>('answered');
  const [note, setNote] = useState('');
  const close = useCloseProblemReport(report.id);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    close.mutate({ status, resolutionNote: note.trim() }, { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Modal open onOpenChange={onOpenChange} title={t('inventory.reports.closeTitle')}>
      <form onSubmit={submit} noValidate aria-busy={close.isPending} data-close-report={report.id}>
        <Field id="close-report-status" label={t('inventory.reports.closeOutcome')}>
          <Select id="close-report-status" value={status} onChange={(event) => setStatus(event.target.value as ProblemReportClosingStatus)}>
            {CLOSING_STATUSES.map((option) => (
              <option key={option} value={option}>
                {t(OPTION_LABEL[option])}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="close-report-note" label={t('inventory.reports.closeNote')} hint={t('inventory.reports.closeNoteHint')}>
          <TextArea id="close-report-note" value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
        {close.isError ? <ProblemAlert error={close.error} codes={{ already_closed: t('inventory.reports.alreadyClosed') }} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={note.trim() === '' || close.isPending || problemStatus(close.error) === 409}>
            {t('inventory.reports.closeSend')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function ReportRow({ report, closable, onClose }: { report: ProblemReport; closable: boolean; onClose: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const locale = useLocale();
  const context = contextLine(report, (code) => languageName(code, locale), t);
  return (
    <Row data-report-id={report.id} data-report-status={report.status}>
      <div className="mb-1.5">
        <PillRow pills={presentProblemReport(report, t)} />
      </div>
      <p className="whitespace-pre-line" data-report-text="">
        {report.description}
      </p>
      <Meta className="mt-1.5">
        <span>{t('inventory.reports.reportedBy', { name: report.reporter.name, time: formatDateTime(report.createdAt, ctx) })}</span>
        {context === null ? null : <span data-report-context="">{context}</span>}
      </Meta>
      {report.closedBy !== null && report.closedAt !== null ? (
        <div className="mt-2 border-t border-line pt-2" data-report-closed="">
          <p className="whitespace-pre-line" data-report-note="">
            {report.resolutionNote}
          </p>
          <Meta className="mt-1">{t('inventory.reports.closedBy', { name: report.closedBy.name, time: formatDateTime(report.closedAt, ctx) })}</Meta>
        </div>
      ) : null}
      {closable ? (
        <Button variant="outline" size="small" className="mt-2" onClick={onClose}>
          {t('inventory.reports.close')}
        </Button>
      ) : null}
    </Row>
  );
}

export function RecordProblemReports({ subjectType, subjectId }: { subjectType: ProblemReportSubjectType; subjectId: string }) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const meId = useSession().me?.user.id ?? null;
  const allowed = permissions.includes(REPORT_PERMISSION);
  const reports = useRecordProblemReports(subjectType, subjectId, allowed);
  const [closing, setClosing] = useState<ProblemReport | null>(null);

  if (!allowed) return null;
  const items = reports.data?.items ?? [];
  const total = reports.data?.total ?? 0;

  return (
    <Panel title={t('inventory.reports.title')} data-problem-reports="">
      <p className="text-meta text-muted">{t(permissions.includes(CLOSE_ANY_PERMISSION) ? 'inventory.reports.introAll' : 'inventory.reports.introOwn')}</p>
      <p className="mb-3 text-meta text-muted" data-reports-watch="">
        {t('inventory.reports.watchCorrects')}
      </p>
      {reports.isPending ? (
        <LoadingState rows={1} />
      ) : reports.isError ? (
        problemStatus(reports.error) === 403 ? (
          <ProblemAlert error={reports.error} />
        ) : (
          <ErrorState title={t('inventory.reports.errorTitle')} onRetry={() => void reports.refetch()} />
        )
      ) : items.length === 0 ? (
        <p className="text-meta text-muted" data-reports-empty="">
          {t('inventory.reports.empty')}
        </p>
      ) : (
        <>
          <Rows>
            {items.map((report) => (
              <ReportRow key={report.id} report={report} closable={canClose(report, meId, permissions)} onClose={() => setClosing(report)} />
            ))}
          </Rows>
          {total > items.length ? <Meta className="mt-3">{t('inventory.reports.more', { shown: items.length, total })}</Meta> : null}
        </>
      )}
      {closing === null ? null : <CloseReportModal report={closing} onOpenChange={(open) => (open ? undefined : setClosing(null))} />}
    </Panel>
  );
}
