'use client';

import Link from 'next/link';
import { useId, useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextArea, TextInput } from '@/components/ui/Field';
import { Notice } from '@/components/ui/Notice';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { aiBasisLabel, citationLabel, isCutShort, presentStatement } from '@/features/search/ask-presentation';
import { useAsk, useRateAnswer, type AskState } from '@/features/search/hooks';
import type { Answer, AnswerStatement, AskRequestBody } from '@/features/search/types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import type { FormatContext } from '@/shared/utils/format';
import { NETWORK_PROBLEM_CODE, problemFrom } from '@/shared/utils/problem';

// Ask, the second mode of /search (design/screens/tenant-ask.html; SRC-03,
// AC-SRC2, AUD-02). The answer streams in statement by statement, each with
// its numbered citations and any pending change flagged; the sources arrive
// with the closing answer. It stays labelled AI output with its basis and
// "as of" date, and a reader can say whether it helped.
//
// The question is the bank's own words (D-07): it lives in component state
// and the request alone, never in the URL, storage or the logger.

export function AskPanel({ asOf, lang, onSearchInstead }: { asOf: string; lang: string; onSearchInstead: (question: string) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const { state, ask } = useAsk();
  const [draft, setDraft] = useState('');
  // The question the answer on screen is for, which "Search instead" carries over.
  const [asked, setAsked] = useState('');

  const send = (question: string) => {
    const body: AskRequestBody = { question };
    if (asOf !== '') body.asOf = asOf;
    if (lang !== '') body.lang = lang;
    setAsked(question);
    ask(body);
  };

  return (
    <>
      <form
        role="search"
        className="mb-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const question = draft.trim();
          if (question !== '') send(question);
        }}
      >
        <TextInput
          type="search"
          className="flex-1"
          aria-label={t('search.ask.questionLabel')}
          placeholder={t('search.ask.placeholder')}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button type="submit" disabled={state.phase === 'streaming'}>
          {t('search.ask.action')}
        </Button>
      </form>
      <AskResult state={state} onRetry={() => send(asked)} onSearchInstead={() => onSearchInstead(asked)} t={t} ctx={ctx} />
    </>
  );
}

function AskResult({ state, onRetry, onSearchInstead, t, ctx }: { state: AskState; onRetry: () => void; onSearchInstead: () => void; t: Translate; ctx: FormatContext }) {
  switch (state.phase) {
    case 'idle':
      return (
        <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-ask-start="">
          <h2 className="text-fg">{t('search.ask.empty.title')}</h2>
          <p className="mx-auto mt-2 max-w-[60ch]">{t('search.ask.empty.body')}</p>
        </div>
      );
    case 'streaming':
      if (state.statements.length === 0) return <LoadingState rows={2} />;
      return (
        <section className="mb-4 rounded-card border border-sand-2 bg-sand p-5" aria-busy="true" data-ask-answer="streaming">
          <AiLabel text={t('search.ask.aiLabelDrafting')} />
          <Statements statements={state.statements} t={t} ctx={ctx} />
        </section>
      );
    case 'answered':
      return state.answer.noAnswer ? <NoAnswer onSearchInstead={onSearchInstead} t={t} /> : <AnswerPanel answer={state.answer} stopReason={state.stopReason} t={t} ctx={ctx} />;
    case 'problem':
      return <ErrorState title={t('search.ask.errorTitle')} onRetry={onRetry} />;
    case 'failed':
      return <AskFailure error={state.error} onRetry={onRetry} onSearchInstead={onSearchInstead} t={t} />;
  }
}

// A refusal before the stream: the bank's switch, a missing permission, a
// limit, or the server not answering at all.
function AskFailure({ error, onRetry, onSearchInstead, t }: { error: unknown; onRetry: () => void; onSearchInstead: () => void; t: Translate }) {
  const problem = problemFrom(error);
  if (problem?.code === 'feature_off') {
    return (
      <Notice className="flex flex-wrap items-center gap-2" data-ask-feature-off="">
        <span>{t('search.ask.featureOff')}</span>
        <Button variant="outline" size="small" onClick={onSearchInstead}>
          {t('search.ask.searchInstead')}
        </Button>
      </Notice>
    );
  }
  const forbidden = forbiddenFrom(error);
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (problem !== null && problem.code !== NETWORK_PROBLEM_CODE && problem.status < 500) return <ProblemAlert error={error} />;
  return <ErrorState title={t('search.ask.errorTitle')} onRetry={onRetry} />;
}

function NoAnswer({ onSearchInstead, t }: { onSearchInstead: () => void; t: Translate }) {
  return (
    <section className="mb-4 rounded-card border border-sand-2 bg-sand p-5" data-ask-answer="none">
      <h2 className="mb-1.5">{t('search.ask.noAnswer.title')}</h2>
      <p>{t('search.ask.noAnswer.body')}</p>
      <ButtonBar className="justify-start">
        <Button variant="outline" size="small" onClick={onSearchInstead}>
          {t('search.ask.searchInstead')}
        </Button>
      </ButtonBar>
    </section>
  );
}

function AiLabel({ text }: { text: string }) {
  return (
    <div className="mb-3 rounded-control bg-surface px-3.5 py-3">
      <span className="block text-meta font-semibold text-brass">{text}</span>
    </div>
  );
}

function Statements({ statements, t, ctx }: { statements: readonly AnswerStatement[]; t: Translate; ctx: FormatContext }) {
  return (
    <>
      {statements.map((statement, index) => {
        const pills = presentStatement(statement, t, ctx);
        return (
          <div key={index} className="mb-3 max-w-[70ch]" data-ask-statement="">
            <p className="mb-1">
              {statement.text}
              <sup className="ml-0.5 font-semibold text-brass">{statement.citationIndexes.join(', ')}</sup>
            </p>
            {pills.length > 0 ? <PillRow pills={pills} /> : null}
          </div>
        );
      })}
    </>
  );
}

function AnswerPanel({ answer, stopReason, t, ctx }: { answer: Answer; stopReason: string | null; t: Translate; ctx: FormatContext }) {
  const citations = [...answer.citations].sort((a, b) => a.index - b.index);
  return (
    <section className="mb-4 rounded-card border border-sand-2 bg-sand p-5" data-ask-answer="done">
      {answer.aiGenerated ? <AiLabel text={aiBasisLabel(answer.asOf, t, ctx)} /> : null}
      <Statements statements={answer.statements} t={t} ctx={ctx} />
      {isCutShort(stopReason) ? (
        <p className="mb-3 text-meta font-semibold" data-ask-cut-short="">
          {t('search.ask.cutShort')}
        </p>
      ) : null}
      <ol aria-label={t('search.ask.citationsLabel')} className="mt-2 list-decimal pl-5 text-meta text-muted">
        {citations.map((citation) => (
          <li key={citation.index} value={citation.index}>
            <Link href={`/inventory/obligations/${citation.obligationId}`} prefetch={false} className="text-fg underline">
              {citationLabel(citation, t)}
            </Link>
          </li>
        ))}
      </ol>
      <AnswerFeedback key={answer.id} answerId={answer.id} t={t} />
    </section>
  );
}

// Helpful, or Wrong with a reason (AUD-02): the verdict is written beside the
// answer's AI log row and read back by the evaluation set.
function AnswerFeedback({ answerId, t }: { answerId: string; t: Translate }) {
  const rate = useRateAnswer(answerId);
  const [explaining, setExplaining] = useState(false);
  const [note, setNote] = useState('');
  const reasonId = useId();

  if (rate.isSuccess) {
    return (
      <p role="status" className="mt-3 text-meta text-positive">
        {t('search.ask.feedback.thanks')}
      </p>
    );
  }
  return (
    <div className="mt-3" data-ask-feedback="">
      {explaining ? (
        <div className="max-w-[640px] rounded-card border border-line bg-surface p-4">
          <Field id={reasonId} label={t('search.ask.feedback.reasonLabel')} hint={t('search.ask.feedback.reasonHint')}>
            <TextArea
              id={reasonId}
              aria-describedby={`${reasonId}-hint`}
              placeholder={t('search.ask.feedback.reasonPlaceholder')}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>
          <ButtonBar>
            <Button variant="outline" size="small" onClick={() => setExplaining(false)}>
              {t('search.ask.feedback.cancel')}
            </Button>
            <Button size="small" disabled={note.trim() === '' || rate.isPending} onClick={() => rate.mutate({ feedback: 'wrong', note: note.trim() })}>
              {t('search.ask.feedback.send')}
            </Button>
          </ButtonBar>
        </div>
      ) : (
        <ButtonBar className="justify-start">
          <Button variant="outline" size="small" onClick={() => setExplaining(true)}>
            {t('search.ask.feedback.wrong')}
          </Button>
          <Button variant="outline" size="small" disabled={rate.isPending} onClick={() => rate.mutate({ feedback: 'helpful', note: '' })}>
            {t('search.ask.feedback.helpful')}
          </Button>
        </ButtonBar>
      )}
      <ProblemAlert error={rate.error} />
    </div>
  );
}
