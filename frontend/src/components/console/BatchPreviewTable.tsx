'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select } from '@/components/ui/Field';
import { PillRow } from '@/components/ui/PillRow';
import { batchRowPills, batchRowTitle, type RowDraft } from '@/features/proposals/batch-presentation';
import { scopeTermPills } from '@/features/proposals/proposal-presentation';
import type { ProposalBatchRow } from '@/features/proposals/types';
import type { VocabularyRow } from '@/features/vocabularies/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// The batch preview (design/screens/console-queue-batch.html, sections 2, 3 and 10;
// PRO-04). A list of cards rather than a table, so it reads at 375 px without sideways
// scrolling: before and after sit side by side from 768 px and stack below it. A row
// is decided here as a draft, undoable until the batch is applied; a rejection always
// carries a reason key from the `rejection_reason` vocabulary. A stale row, previewed
// against a scope its record no longer has, can only be rejected. A row the server has
// decided shows its decision and nothing to change.

function Terms({ refs, labelOf }: { refs: readonly string[]; labelOf: (ref: string) => string }) {
  const t = useT();
  if (refs.length === 0) return <p className="text-meta text-muted">{t('console.batch.noTerms')}</p>;
  return <PillRow pills={scopeTermPills(refs, labelOf)} />;
}

function RejectRowForm({ rowId, reasons, onReject, onCancel }: { rowId: string; reasons: readonly VocabularyRow[]; onReject: (code: string) => void; onCancel: () => void }) {
  const t = useT();
  const [code, setCode] = useState('');
  const [tried, setTried] = useState(false);
  const id = `reject-row-${rowId}`;
  return (
    <form
      className="mt-2"
      aria-label={t('console.batch.row.rejectSubmit')}
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (code !== '') onReject(code);
      }}
    >
      <Field id={id} label={t('console.batch.row.reason')} error={tried && code === '' ? t('console.batch.row.reasonRequired') : undefined}>
        <Select id={id} value={code} onChange={(event) => setCode(event.target.value)} aria-invalid={tried && code === ''}>
          <option value="">{t('console.batch.row.reasonPlaceholder')}</option>
          {reasons.map((reason) => (
            <option key={reason.key} value={reason.key}>
              {reason.label}
            </option>
          ))}
        </Select>
      </Field>
      <ButtonBar className="mt-2">
        <Button variant="outline" size="small" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button size="small" type="submit">
          {t('console.batch.row.rejectSubmit')}
        </Button>
      </ButtonBar>
    </form>
  );
}

function BatchRowCard({
  row,
  draft,
  editable,
  reasons,
  labelOf,
  onDraft,
}: {
  row: ProposalBatchRow;
  draft: RowDraft | undefined;
  editable: boolean;
  reasons: readonly VocabularyRow[];
  labelOf: (ref: string) => string;
  onDraft: (draft: RowDraft | null) => void;
}) {
  const t = useT();
  const [rejecting, setRejecting] = useState(false);
  const pending = row.decision === 'pending';
  const reasonKey = pending ? draft?.rejectionCode : row.rejectionCode;
  const reason = reasonKey === undefined || reasonKey === '' ? null : (reasons.find((r) => r.key === reasonKey)?.label ?? reasonKey);
  const decided = !pending || draft !== undefined;

  return (
    <div
      className={decided ? 'rounded-card border border-line bg-subtle px-4 py-3' : 'rounded-card border border-line bg-surface px-4 py-3'}
      data-batch-row={row.id}
      data-batch-row-decision={pending ? (draft?.decision ?? 'pending') : row.decision}
    >
      <PillRow pills={batchRowPills(row, draft, t)} />
      <h3 className="mt-1.5 font-semibold break-words">{batchRowTitle(row)}</h3>
      <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="min-w-0">
          <p className="microlabel mb-1 text-muted">{t('console.batch.before')}</p>
          <Terms refs={row.before.terms ?? []} labelOf={labelOf} />
        </div>
        <div className="min-w-0">
          <p className="microlabel mb-1 text-muted">{t('console.batch.after')}</p>
          <Terms refs={row.after.terms ?? []} labelOf={labelOf} />
        </div>
      </div>
      {row.source !== undefined && row.source.startsWith('https://') ? (
        <a href={row.source} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-meta underline">
          {t('console.batch.rowSource')}
        </a>
      ) : null}
      {row.stale === true && pending ? <p className="mt-2 text-meta text-muted">{t('console.batch.row.staleHint')}</p> : null}
      {reason !== null ? <p className="mt-2 text-meta text-muted">{reason}</p> : null}
      {editable && pending ? (
        rejecting ? (
          <RejectRowForm
            rowId={row.id}
            reasons={reasons}
            onCancel={() => setRejecting(false)}
            onReject={(code) => {
              setRejecting(false);
              onDraft({ decision: 'rejected', rejectionCode: code });
            }}
          />
        ) : draft !== undefined ? (
          <ButtonBar className="mt-3">
            <Button variant="ghost" size="small" onClick={() => onDraft(null)}>
              {t('console.batch.row.undo')}
            </Button>
          </ButtonBar>
        ) : (
          <ButtonBar className="mt-3">
            <Button variant="outline" size="small" onClick={() => setRejecting(true)}>
              {t('console.batch.row.reject')}
            </Button>
            {row.stale === true ? null : (
              <Button size="small" onClick={() => onDraft({ decision: 'approved', rejectionCode: '' })}>
                {t('console.batch.row.approve')}
              </Button>
            )}
          </ButtonBar>
        )
      ) : null}
    </div>
  );
}

export function BatchPreviewTable({
  rows,
  drafts,
  editable,
  reasons,
  labelOf,
  onDraft,
}: {
  rows: readonly ProposalBatchRow[];
  drafts: ReadonlyMap<string, RowDraft>;
  editable: boolean;
  reasons: readonly VocabularyRow[];
  labelOf: (ref: string) => string;
  onDraft: (rowId: string, draft: RowDraft | null) => void;
}) {
  return (
    <div className="grid gap-2" data-batch-rows="">
      {rows.map((row) => (
        <BatchRowCard key={row.id} row={row} draft={drafts.get(row.id)} editable={editable} reasons={reasons} labelOf={labelOf} onDraft={(draft) => onDraft(row.id, draft)} />
      ))}
    </div>
  );
}
