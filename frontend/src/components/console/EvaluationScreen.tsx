'use client';

import { useState, type FormEvent, type ReactNode } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import type { EvalBaseline, EvalQuestion, EvalQuestionInput, EvalRun } from '@/features/evaluation/api';
import { formatBaseline, formatScore, languageLabel, languageOptions, MATCH_KIND_KEY, METRICS, presentQuestion, presentRun } from '@/features/evaluation/evaluation-presentation';
import { useCreateEvalQuestion, useEvalBaseline, useEvalQuestions, useEvalRuns } from '@/features/evaluation/hooks';
import { useFormatContext } from '@/features/identity/hooks';
import { useLanguages } from '@/features/tenant-admin/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// Evaluation (design/screens/console-evaluation.html, SRC-05, ADM-02): the
// questions the release gate scores search with, the baseline it holds search
// to, and the runs recorded against the set. A question added here is kept
// and scored by recorded runs, but the gate reads only its own file, so the
// form and the new row both say it is not yet in the gate. A baseline nobody
// recorded reads "Unrecorded", never zero.

type Languages = readonly { key: string; label: string }[] | undefined;

function BaselinePanel({ baseline, latest }: { baseline: EvalBaseline; latest: EvalRun | undefined }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Panel title={t('console.evaluation.baseline.title')} data-eval-baseline="">
      <p className="-mt-1.5 mb-3 text-meta text-muted">
        {baseline.recordedAt === null ? t('console.evaluation.baseline.notRecorded') : t('console.evaluation.baseline.recordedOn', { date: formatDateTime(baseline.recordedAt, ctx) })}
      </p>
      <dl className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-x-4 gap-y-2">
        <dt className="text-meta text-muted">{t('console.evaluation.metric.label')}</dt>
        <dd className="m-0 text-meta text-muted">{t('console.evaluation.baseline.column')}</dd>
        <dd className="m-0 text-meta text-muted">{t('console.evaluation.baseline.latest')}</dd>
        {METRICS.map((metric) => (
          <MetricRow key={metric.key} label={t(metric.labelKey)} metric={metric.key}>
            <dd className="m-0" data-baseline-value="">
              {formatBaseline(baseline[metric.key], t, ctx)}
            </dd>
            <dd className="m-0" data-latest-value="">
              {latest === undefined ? t('console.evaluation.baseline.noRun') : formatScore(latest.metrics.overall[metric.key], ctx)}
            </dd>
          </MetricRow>
        ))}
      </dl>
    </Panel>
  );
}

function MetricRow({ label, metric, children }: { label: string; metric: string; children: ReactNode }) {
  return (
    <div className="contents" data-baseline-metric={metric}>
      <dt className="font-medium">{label}</dt>
      {children}
    </div>
  );
}

function QuestionRow({ question, languages }: { question: EvalQuestion; languages: Languages }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-question-key={question.key} data-lang={question.lang}>
      <PillRow pills={presentQuestion(question, t, languages)} />
      <h3 className="mt-1.5 mb-1 font-semibold">{question.question}</h3>
      <Meta>
        <code className="font-mono">{question.key}</code>
        <span>{question.expected.length === 0 ? t('console.evaluation.question.expectsNothing') : t('console.evaluation.question.expects', { keys: question.expected.join(', ') })}</span>
        {question.asOf === null ? null : <span>{t('console.evaluation.question.asOf', { date: formatDate(question.asOf, ctx) })}</span>}
      </Meta>
      {question.notes === '' ? null : <p className="mt-1 mb-0 text-meta text-muted">{question.notes}</p>}
    </Row>
  );
}

function RunRow({ run }: { run: EvalRun }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-run-id={run.id}>
      <PillRow pills={presentRun(run.config.isMock, t)} />
      <h3 className="mt-1.5 mb-1 font-semibold">{formatDateTime(run.runAt, ctx)}</h3>
      <Meta>
        <code className="font-mono break-all">{run.config.retriever}</code>
        <span>{t('console.evaluation.runs.questions', { count: run.config.questions })}</span>
        {METRICS.map((metric) => (
          <span key={metric.key}>{t('console.evaluation.runs.score', { metric: t(metric.labelKey), value: formatScore(run.metrics.overall[metric.key], ctx) })}</span>
        ))}
      </Meta>
    </Row>
  );
}

type FormProblem = 'key' | 'lang' | 'question';

const EMPTY_FORM = { key: '', lang: '', question: '', expected: '', matchKind: 'concept' as EvalQuestion['matchKind'], asOf: '', notes: '' };

function AddQuestionModal({ open, onClose, onAdded, languages }: { open: boolean; onClose: () => void; onAdded: (question: EvalQuestion) => void; languages: Languages }) {
  const t = useT();
  const create = useCreateEvalQuestion();
  const [form, setForm] = useState(EMPTY_FORM);
  const [problem, setProblem] = useState<FormProblem | null>(null);
  const set = (field: keyof typeof EMPTY_FORM) => (event: { target: { value: string } }) => setForm((current) => ({ ...current, [field]: event.target.value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (form.key.trim() === '') return setProblem('key');
    if (form.lang === '') return setProblem('lang');
    if (form.question.trim() === '') return setProblem('question');
    setProblem(null);
    const body: EvalQuestionInput = {
      key: form.key.trim(),
      lang: form.lang,
      question: form.question.trim(),
      expected: form.expected
        .split(/[\s,]+/)
        .map((key) => key.trim())
        .filter((key) => key !== ''),
      matchKind: form.matchKind,
      // A question added here is scored on search's hits; the gate's file marks the few Ask rows.
      via: 'search',
      notes: form.notes.trim(),
      ...(form.asOf === '' ? {} : { asOf: form.asOf }),
    };
    create.mutate(body, {
      onSuccess: (question) => {
        onAdded(question);
        setForm(EMPTY_FORM);
        onClose();
      },
    });
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={t('console.evaluation.add.title')}>
      <form onSubmit={submit} noValidate aria-busy={create.isPending} data-eval-question-form="">
        <p className="mb-3 rounded-control bg-warning-soft px-3 py-2.5" data-not-in-gate="">
          {t('console.evaluation.add.notInGate')}
        </p>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="eval-key" label={t('console.evaluation.add.key')} hint={t('console.evaluation.add.keyHint')} error={problem === 'key' ? t('console.evaluation.add.keyRequired') : undefined}>
            <TextInput id="eval-key" value={form.key} placeholder={t('console.evaluation.add.keyPlaceholder')} onChange={set('key')} />
          </Field>
          <Field id="eval-lang" label={t('console.evaluation.add.lang')} error={problem === 'lang' ? t('console.evaluation.add.langRequired') : undefined}>
            <Select id="eval-lang" value={form.lang} disabled={languages === undefined} onChange={set('lang')}>
              <option value="">{t('console.evaluation.add.langChoose')}</option>
              {languages?.map((language) => (
                <option key={language.key} value={language.key}>
                  {languageLabel(language.key, languages)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field id="eval-question" label={t('console.evaluation.add.question')} hint={t('console.evaluation.add.questionHint')} error={problem === 'question' ? t('console.evaluation.add.questionRequired') : undefined}>
          <TextInput id="eval-question" value={form.question} placeholder={t('console.evaluation.add.questionPlaceholder')} onChange={set('question')} />
        </Field>
        <Field id="eval-expected" label={t('console.evaluation.add.expected')} hint={t('console.evaluation.add.expectedHint')}>
          <TextArea id="eval-expected" value={form.expected} placeholder={t('console.evaluation.add.expectedPlaceholder')} onChange={set('expected')} />
        </Field>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="eval-match" label={t('console.evaluation.add.matchKind')} hint={t('console.evaluation.add.matchKindHint')}>
            <Select id="eval-match" value={form.matchKind} onChange={set('matchKind')}>
              {(Object.keys(MATCH_KIND_KEY) as EvalQuestion['matchKind'][]).map((kind) => (
                <option key={kind} value={kind}>
                  {t(MATCH_KIND_KEY[kind])}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="eval-as-of" label={t('console.evaluation.add.asOf')} hint={t('console.evaluation.add.asOfHint')}>
            <TextInput id="eval-as-of" type="date" value={form.asOf} onChange={set('asOf')} />
          </Field>
        </div>
        <Field id="eval-notes" label={t('console.evaluation.add.notes')} hint={t('console.evaluation.add.notesHint')}>
          <TextArea id="eval-notes" value={form.notes} onChange={set('notes')} />
        </Field>
        {create.isError ? <ProblemAlert error={create.error} codes={{ duplicate_key: t('console.evaluation.add.duplicateKey') }} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={create.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('console.evaluation.add.submit')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function EvaluationScreen() {
  const t = useT();
  const questions = useEvalQuestions();
  const runs = useEvalRuns();
  const baseline = useEvalBaseline();
  const languages = useLanguages();
  const [lang, setLang] = useState('');
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState<EvalQuestion | null>(null);

  const head = <PageHead title={t('console.evaluation.title')} lede={t('console.evaluation.lede')} actions={<Button onClick={() => setAdding(true)}>{t('console.evaluation.add.open')}</Button>} />;
  const modal = <AddQuestionModal open={adding} onClose={() => setAdding(false)} onAdded={setAdded} languages={languages.data} />;

  if (questions.isPending || runs.isPending || baseline.isPending) {
    return (
      <>
        {head}
        <LoadingState rows={3} />
      </>
    );
  }
  if (questions.isError || runs.isError || baseline.isError) {
    return (
      <>
        {head}
        <ErrorState
          title={t('console.evaluation.errorTitle')}
          onRetry={() => {
            void questions.refetch();
            void runs.refetch();
            void baseline.refetch();
          }}
        />
      </>
    );
  }

  const options = languageOptions(questions.data, languages.data);
  const shown = lang === '' ? questions.data : questions.data.filter((question) => question.lang === lang);

  return (
    <>
      {head}
      {added === null ? null : <StatusLine tone="positive">{t('console.evaluation.add.added', { key: added.key })}</StatusLine>}
      <BaselinePanel baseline={baseline.data} latest={runs.data.items[0]} />

      <section className="mb-6" aria-labelledby="eval-questions-title">
        <h2 id="eval-questions-title" className="mb-3">
          {t('console.evaluation.questions.title')}
        </h2>
        {questions.data.length === 0 ? (
          <EmptyState title={t('console.evaluation.questions.emptyTitle')} body={t('console.evaluation.questions.emptyBody')} />
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Select aria-label={t('console.evaluation.questions.filter')} className="w-auto" value={lang} onChange={(e) => setLang(e.target.value)}>
                <option value="">{t('console.evaluation.questions.anyLanguage')}</option>
                {options.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </Select>
              <Meta>
                <span>{t('console.evaluation.questions.count', { shown: shown.length, total: questions.data.length })}</span>
              </Meta>
            </div>
            <Rows data-eval-questions="">
              {shown.map((question) => (
                <QuestionRow key={question.id} question={question} languages={languages.data} />
              ))}
            </Rows>
          </>
        )}
      </section>

      <section aria-labelledby="eval-runs-title">
        <h2 id="eval-runs-title" className="mb-3">
          {t('console.evaluation.runs.title')}
        </h2>
        {runs.data.items.length === 0 ? (
          <EmptyState title={t('console.evaluation.runs.emptyTitle')} body={t('console.evaluation.runs.emptyBody')} />
        ) : (
          <>
            <Rows data-eval-runs="">
              {runs.data.items.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </Rows>
            <Meta className="mt-3">
              <span>{t('console.evaluation.runs.count', { shown: runs.data.items.length, total: runs.data.total })}</span>
            </Meta>
          </>
        )}
      </section>
      {modal}
    </>
  );
}
