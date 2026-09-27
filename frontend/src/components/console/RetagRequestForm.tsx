'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { retagInFlight, useCreateRetagRequest, useRetagRequest, useRetagTerms } from '@/features/proposals/hooks';
import { nearMatches } from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Ask for a re-tag" (design/screens/console-queue-batch.html, section 8; AGT-05,
// PRO-04). It files a research request, never an edit: bleqq's agent answers it with
// one batch proposal that a second library editor decides in the queue. The term is
// matched against the live taxonomy with the vocabulary picker's own near match, so a
// near miss offers the term that exists. The request is a job: the form reads its
// status until the batch appears, then links to it. The console shell and the queue's
// `proposals.review` gate are the only way here; the server refuses anyone else.

type Change = 'add' | 'remove';

function isChange(value: string): value is Change {
  return value === 'add' || value === 'remove';
}

function RetagStatus({ requestId }: { requestId: string }) {
  const t = useT();
  const request = useRetagRequest(requestId);
  if (request.isError) return <ProblemAlert error={request.error} />;
  const batchId = request.data?.batchProposalId ?? null;
  if (batchId !== null) {
    return (
      <p role="status" className="mt-2.5 flex flex-wrap gap-x-1.5 text-meta" data-retag-batch={batchId}>
        <span>{t('console.retag.status.ready')}</span>
        <Link href={`/console/queue/batches/${batchId}`} className="underline">
          {t('console.retag.status.openBatch')}
        </Link>
      </p>
    );
  }
  if (request.data !== undefined && !retagInFlight(request.data)) return <StatusLine>{t('console.retag.status.noBatch')}</StatusLine>;
  return <StatusLine>{t('console.retag.status.working')}</StatusLine>;
}

export function RetagRequestForm({ onClose }: { onClose: () => void }) {
  const t = useT();
  const terms = useRetagTerms();
  const create = useCreateRetagRequest();
  const [change, setChange] = useState<Change>('add');
  const [termText, setTermText] = useState('');
  const [records, setRecords] = useState('');
  const [why, setWhy] = useState('');
  const [requestId, setRequestId] = useState<string | null>(null);

  const candidates = (terms.data ?? []).map((term) => ({ ...term, ref: `${term.dimension}:${term.key}`, active: true }));
  const { exact, matches } = nearMatches(termText, candidates);
  const nearest = exact === null && termText.trim() !== '' ? (matches[0] ?? null) : null;
  const canSubmit = exact !== null && records.trim() !== '' && !create.isPending && requestId === null;

  const submit = () => {
    if (exact === null) return;
    const vars = { term: exact.label, ref: exact.ref, records: records.trim() };
    const asked = t(change === 'add' ? 'console.retag.topic.add' : 'console.retag.topic.remove', vars);
    const topic = why.trim() === '' ? asked : `${asked} ${t('console.retag.topic.why', { why: why.trim() })}`;
    create.mutate({ topic }, { onSuccess: (request) => setRequestId(request.id) });
  };

  return (
    <Panel className="mb-4" aria-labelledby="retag-title" data-retag-form="">
      <h2 id="retag-title" className="mb-3 text-title">
        {t('console.retag.title')}
      </h2>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (canSubmit) submit();
        }}
      >
        <Field id="retag-change" label={t('console.retag.change')}>
          <Select id="retag-change" value={change} onChange={(event) => setChange(isChange(event.target.value) ? event.target.value : 'add')}>
            <option value="add">{t('console.retag.change.add')}</option>
            <option value="remove">{t('console.retag.change.remove')}</option>
          </Select>
        </Field>
        <Field
          id="retag-term"
          label={t('console.retag.term')}
          hint={t('console.retag.termHint')}
          error={termText.trim() !== '' && exact === null && nearest === null && terms.isSuccess ? t('console.retag.termUnknown') : undefined}
        >
          <TextInput id="retag-term" placeholder={t('console.retag.termPlaceholder')} value={termText} onChange={(event) => setTermText(event.target.value)} aria-invalid={termText.trim() !== '' && exact === null} />
        </Field>
        {nearest !== null ? (
          <p role="alert" className="-mt-1 mb-3 flex flex-wrap items-center gap-x-2 text-meta" data-retag-near-match={nearest.ref}>
            {t('console.retag.didYouMean', { label: nearest.label })}
            <Button variant="ghost" size="small" onClick={() => setTermText(nearest.label)}>
              {t('console.retag.useTerm', { label: nearest.label })}
            </Button>
          </p>
        ) : null}
        <Field id="retag-records" label={t('console.retag.records')}>
          <TextArea id="retag-records" placeholder={t('console.retag.recordsPlaceholder')} value={records} onChange={(event) => setRecords(event.target.value)} />
        </Field>
        <Field id="retag-why" label={t('console.retag.why')} hint={t('common.optional')}>
          <TextArea id="retag-why" placeholder={t('console.retag.whyPlaceholder')} value={why} onChange={(event) => setWhy(event.target.value)} />
        </Field>
        <ProblemAlert error={create.error} />
        <ButtonBar>
          <Button variant="outline" onClick={onClose}>
            {requestId === null ? t('common.cancel') : t('common.done')}
          </Button>
          <Button type="submit" disabled={!canSubmit}>
            {t('console.retag.submit')}
          </Button>
        </ButtonBar>
        <p className="mt-2 text-meta text-muted">{t('console.retag.footnote')}</p>
      </form>
      {requestId !== null ? <RetagStatus requestId={requestId} /> : null}
    </Panel>
  );
}
