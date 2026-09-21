'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { ProblemAlert } from '@/components/ui/States';
import type { ProblemReportBody, ProblemReportCreated } from '@/features/library/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// "This looks wrong" (design/screens/tenant-obligation.html; INV-06, INV-S7).
// The report is the reader's own words about a shared record: it is the bank's
// content, so it is never logged here and never sent anywhere but the route
// that stores it inside that bank. The mutation is the caller's, which is what
// lets the instrument card file its own reports through the same form.
//
// There is no "Where" select: the field the prototype drew is not a code enum
// and not yet a vocabulary, so the form takes the description alone
// (docs/plans/briefs/CHUNK3_TASKS.md, open questions).

export interface ReportContext {
  /** The version the reader had on screen, so a colleague opens the same words. */
  versionNumber?: number;
  /** The content language they were reading. */
  language?: string;
}

export interface ReportMutation {
  mutate: (body: ProblemReportBody) => void;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  data: ProblemReportCreated | undefined;
  reset: () => void;
}

export function ReportProblemModal({ open, onOpenChange, context, report }: { open: boolean; onOpenChange: (open: boolean) => void; context: ReportContext; report: ReportMutation }) {
  const t = useT();
  const [description, setDescription] = useState('');

  const close = () => {
    setDescription('');
    report.reset();
    onOpenChange(false);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    report.mutate({ description: description.trim(), ...context });
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())} title={t('inventory.obligation.reportTitle')}>
      {report.data === undefined ? (
        <form onSubmit={submit} noValidate aria-busy={report.isPending}>
          <Field id="report-description" label={t('inventory.obligation.reportField')} hint={t('inventory.obligation.reportHint')}>
            <TextArea
              id="report-description"
              value={description}
              placeholder={t('inventory.obligation.reportPlaceholder')}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
          {report.isError ? <ProblemAlert error={report.error} /> : null}
          <ButtonBar>
            <Button variant="outline" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={description.trim() === '' || report.isPending}>
              {t('inventory.obligation.reportSend')}
            </Button>
          </ButtonBar>
        </form>
      ) : (
        <>
          <p role="status" className="text-positive" data-report-sent="">
            {t('inventory.obligation.reportSent')}
          </p>
          <ButtonBar>
            <Button onClick={close}>{t('common.done')}</Button>
          </ButtonBar>
        </>
      )}
    </Modal>
  );
}
