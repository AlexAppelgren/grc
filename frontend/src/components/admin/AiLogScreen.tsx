'use client';

import Link from 'next/link';
import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Select } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { AI_PURPOSES, AI_REVIEW_STATES, keepsAiLabel, presentAiGeneration, purposeLabel, reviewLabel } from '@/features/governance/ai-log-presentation';
import { subjectTypeLabel } from '@/features/governance/audit-presentation';
import { AI_LOG_PAGE, useAiGenerations } from '@/features/governance/hooks';
import type { AiGeneration } from '@/features/governance/types';
import { useFormatContext } from '@/features/identity/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';

// The AI log (AUD-02; design/screens/admin-ai-log.html). Every model call the
// bank can see, newest first, with its purpose, model, review state, sources
// and a reader's verdict. A row opens to what the model wrote, and the AI
// label stays on it until a person confirmed the words as they stand. The
// filters are the route's: purpose, review state, and one record, picked from
// a row as on the audit log.

interface Picked {
  id: string;
  label: string;
}

export function AiLogScreen() {
  const t = useT();
  const [purpose, setPurpose] = useState('');
  const [status, setStatus] = useState('');
  const [record, setRecord] = useState<Picked | null>(null);
  const [offset, setOffset] = useState(0);

  // A changed filter starts again at the first page.
  function on<T>(set: (value: T) => void): (value: T) => void {
    return (value) => {
      set(value);
      setOffset(0);
    };
  }

  const filtered = purpose !== '' || status !== '' || record !== null;
  const log = useAiGenerations({
    purpose: purpose === '' ? undefined : purpose,
    status: status === '' ? undefined : status,
    subjectId: record?.id,
    offset,
    limit: AI_LOG_PAGE,
  });

  function clear(): void {
    setPurpose('');
    setStatus('');
    setRecord(null);
    setOffset(0);
  }

  const forbidden = forbiddenFrom(log.error);
  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.aiLog.title')} lede={t('admin.aiLog.lede')} />

      <Panel className="grid gap-x-4 md:grid-cols-3" data-ai-filters="">
        <Field id="ai-purpose" label={t('admin.aiLog.filter.purpose')}>
          <Select id="ai-purpose" value={purpose} onChange={(e) => on(setPurpose)(e.target.value)}>
            <option value="">{t('admin.aiLog.filter.anyPurpose')}</option>
            {AI_PURPOSES.map((kind) => (
              <option key={kind} value={kind}>
                {purposeLabel(kind, t)}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="ai-review" label={t('admin.aiLog.filter.review')}>
          <Select id="ai-review" value={status} onChange={(e) => on(setStatus)(e.target.value)}>
            <option value="">{t('admin.aiLog.filter.anyReview')}</option>
            {AI_REVIEW_STATES.map((kind) => (
              <option key={kind} value={kind}>
                {reviewLabel(kind, t)}
              </option>
            ))}
          </Select>
        </Field>
        <Meta className="md:self-end md:pb-4">
          {record !== null ? (
            <Button variant="outline" size="small" onClick={() => on(setRecord)(null)} data-clear-record="">
              {t('admin.aiLog.filter.record', { record: record.label })}
            </Button>
          ) : null}
          {filtered ? (
            <Button variant="ghost" size="small" onClick={clear}>
              {t('admin.aiLog.filter.clear')}
            </Button>
          ) : null}
        </Meta>
      </Panel>

      {log.isPending ? (
        <LoadingState />
      ) : forbidden !== null ? (
        <RestrictedScreen {...forbidden} />
      ) : log.isError ? (
        <ErrorState title={t('admin.aiLog.errorTitle')} onRetry={() => void log.refetch()} />
      ) : log.data.items.length === 0 ? (
        <EmptyState title={t('admin.aiLog.emptyTitle')} body={filtered ? t('admin.aiLog.emptyFiltered') : t('admin.aiLog.emptyBody')} />
      ) : (
        <>
          <Panel className="px-4 py-1" data-ai-log="">
            {log.data.items.map((row) => (
              <AiRow key={row.id} row={row} onRecord={on(setRecord)} />
            ))}
          </Panel>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-meta text-muted">
            <span>{t('admin.aiLog.range', { from: offset + 1, to: Math.min(offset + log.data.items.length, log.data.total), total: log.data.total })}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - AI_LOG_PAGE))}>
                {t('admin.aiLog.newer')}
              </Button>
              <Button variant="outline" size="small" disabled={offset + AI_LOG_PAGE >= log.data.total} onClick={() => setOffset(offset + AI_LOG_PAGE)}>
                {t('admin.aiLog.older')}
              </Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function AiRow({ row, onRecord }: { row: AiGeneration; onRecord: (picked: Picked) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const [open, setOpen] = useState(false);
  const { subjectId } = row;
  // An Ask answer is logged about itself: there is no other record to narrow to.
  const aboutRecord = subjectId !== null && subjectId !== row.id;
  return (
    <div
      className="grid gap-1 border-b border-line py-3 last:border-b-0 md:grid-cols-[170px_1fr] md:gap-x-4"
      data-ai-row=""
      data-generation-id={row.id}
      data-purpose={row.purpose}
      data-status={row.status}
      data-feedback={row.feedback}
    >
      <time dateTime={row.createdAt} className="block text-meta text-muted">
        {formatDateTime(row.createdAt, ctx)}
      </time>
      <div className="min-w-0">
        <PillRow pills={presentAiGeneration(row, t)} />
        <Meta className="mt-1">
          <span>{t('admin.aiLog.model', { model: row.model, version: row.modelVersion })}</span>
          {row.modelMetadataReportedByAgent ? <span>{t('admin.aiLog.reportedByAgent')}</span> : null}
          {aboutRecord ? <span>{subjectTypeLabel(row.subjectType)}</span> : null}
          <span>{t('admin.aiLog.sources', { count: row.citations.length })}</span>
          <Button variant="ghost" size="small" aria-expanded={open} onClick={() => setOpen(!open)} data-toggle-output="">
            {open ? t('admin.aiLog.hide') : t('admin.aiLog.show')}
          </Button>
          {aboutRecord && row.subjectType === 'regulatory_change' ? (
            <Link href={`/watch/${subjectId}`} className="underline">
              {t('admin.aiLog.openChange')}
            </Link>
          ) : null}
          {aboutRecord ? (
            <Button variant="ghost" size="small" onClick={() => onRecord({ id: subjectId, label: subjectTypeLabel(row.subjectType) })} data-only-record="">
              {t('admin.aiLog.onlyRecord')}
            </Button>
          ) : null}
        </Meta>
        {open ? <Output row={row} t={t} ctx={ctx} /> : null}
      </div>
    </div>
  );
}

function reviewLine(row: AiGeneration, t: Translate, ctx: FormatContext): string | null {
  if (row.reviewedBy === null || row.reviewedAt === null) return null;
  const vars = { name: row.reviewedBy.name, time: formatDateTime(row.reviewedAt, ctx) };
  if (row.status === 'confirmed') return t('admin.aiLog.confirmedBy', vars);
  if (row.status === 'edited') return t('admin.aiLog.editedBy', vars);
  if (row.status === 'rejected') return t('admin.aiLog.rejectedBy', vars);
  return null;
}

// What the model wrote, as the log holds it. The AI label comes first and
// stays until a person confirmed the words as they stand (CLAUDE.md
// section 5); who settled it, and when, follows.
function Output({ row, t, ctx }: { row: AiGeneration; t: Translate; ctx: FormatContext }) {
  const reviewed = reviewLine(row, t, ctx);
  return (
    <section className="mt-2 rounded-card border border-sand-2 bg-sand p-4" data-ai-output="">
      {keepsAiLabel(row.status) ? (
        <p className="mb-2 rounded-control bg-surface px-3.5 py-2 text-meta font-semibold text-brass" data-ai-label="">
          {t('admin.aiLog.aiLabel')}
        </p>
      ) : null}
      {reviewed !== null ? (
        <p className="mb-2 rounded-control bg-surface px-3.5 py-2 text-meta font-semibold" data-ai-reviewed="">
          {reviewed}
        </p>
      ) : null}
      <p className="max-w-[70ch] break-words whitespace-pre-line">{row.output}</p>
      {row.citations.length > 0 ? (
        <ol aria-label={t('admin.aiLog.sourcesLabel')} className="mt-2 list-decimal pl-5 text-meta text-muted">
          {row.citations.map((citation, index) => (
            <li key={index}>
              <a href={citation.url} target="_blank" rel="noopener noreferrer" className="break-words text-fg underline">
                {citation.label}
              </a>
            </li>
          ))}
        </ol>
      ) : null}
      {row.feedbackNote !== '' ? (
        <p className="mt-2 text-meta" data-feedback-note="">
          {t('admin.aiLog.reason', { note: row.feedbackNote })}
        </p>
      ) : null}
    </section>
  );
}
