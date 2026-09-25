'use client';

import { useQueries } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { RejectProposalDialog } from '@/components/console/RejectProposalDialog';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { languageName } from '@/features/library/version-presentation';
import { useApproveProposal, useScopeTermLabels } from '@/features/proposals/hooks';
import { obligationPayloadOf } from '@/features/proposals/proposal-presentation';
import type { ProposalRow } from '@/features/proposals/types';
import { listScopeTerms, type ScopeTerm } from '@/features/watch/api';
import { useT } from '@/shared/i18n/LocaleProvider';

/** The remove glyph on a scope chip (design/screens/console-queue.html `.x`): an icon, not copy, so it is not in the catalog. */
const REMOVE_GLYPH = '×';

// "Correct before approving" (design/screens/console-queue.html; PRO-02).
// The form offers only fields this proposal already sources — text per
// language, the effective date, and the scope terms — because
// `POST /proposals/{id}/approve` re-runs the source check over the merged
// payload and refuses (422 `source_missing`) a correction that introduces a
// field the proposal never sourced (backend/apps/proposals/logic.py
// `corrected`). Only `new_obligation_version` proposals reach this form: a
// vocabulary row's label is wording a person writes, not a fact to correct
// against a source, so those kinds reject instead of correct.
//
// A value changed from what was proposed names the source the reviewer read it
// in: the proposer's source vouches only for the value it came with, so the
// server refuses (422 `source_missing`) a changed value without a fresh one in
// `fieldSources`. The form asks for that source once, for every field changed.
//
// The scope editor lets a reviewer remove a term the proposal suggested and
// add another from the same dimensions it already touches, which is what
// PRO-S4 exercises; the shared library's own picker for suggesting a term in
// a dimension the proposal never named belongs to a wider scope editor than
// this correction form needs.

function useDimensionTerms(dimensions: readonly string[]): Record<string, ScopeTerm[]> {
  const results = useQueries({ queries: dimensions.map((dimension) => ({ queryKey: ['watch', 'terms', dimension], queryFn: () => listScopeTerms(dimension), staleTime: 5 * 60_000 })) });
  const byDimension: Record<string, ScopeTerm[]> = {};
  dimensions.forEach((dimension, index) => {
    byDimension[dimension] = results[index]?.data ?? [];
  });
  return byDimension;
}

export function ProposalCorrectionForm({ proposal }: { proposal: ProposalRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const payload = obligationPayloadOf(proposal);
  const sourcedFields = useMemo(() => new Set(Object.keys(proposal.fieldSources ?? {})), [proposal.fieldSources]);
  const proposedTerms = payload?.terms ?? null;
  const termsEditable = sourcedFields.has('terms') && proposedTerms !== null;
  const dateEditable = sourcedFields.has('effectiveFrom');

  const [summaries, setSummaries] = useState<Record<string, string>>(payload?.summaries ?? {});
  const [effectiveFrom, setEffectiveFrom] = useState(payload?.effectiveFrom ?? '');
  const [terms, setTerms] = useState<string[]>(proposedTerms ?? []);
  const [note, setNote] = useState('');
  const [source, setSource] = useState('');
  const [rejecting, setRejecting] = useState(false);

  const dimensions = useMemo(() => [...new Set(terms.map((ref) => ref.split(':')[0]).filter((d): d is string => d !== undefined && d !== ''))], [terms]);
  const { labelOf } = useScopeTermLabels(terms);
  const dimensionTerms = useDimensionTerms(dimensions);
  const addable = dimensions.flatMap((dimension) =>
    (dimensionTerms[dimension] ?? [])
      .filter((term) => !terms.includes(`${dimension}:${term.key}`))
      .map((term) => ({ ref: `${dimension}:${term.key}`, label: term.label })),
  );

  const approve = useApproveProposal(proposal.id);

  if (payload === null) return null;

  // The fields as the server names them whose value now differs from the proposal's.
  const changed = [
    ...Object.entries(summaries)
      .filter(([language, text]) => text !== payload.summaries[language])
      .map(([language]) => `summaries.${language}`),
    ...(dateEditable && effectiveFrom !== (payload.effectiveFrom ?? '') ? ['effectiveFrom'] : []),
    ...(termsEditable && terms.join() !== (proposedTerms ?? []).join() ? ['terms'] : []),
  ];

  const submit = () => {
    approve.mutate({
      note: note.trim(),
      payloadOverrides: {
        summaries,
        effectiveFrom: dateEditable ? (effectiveFrom === '' ? null : effectiveFrom) : undefined,
        ...(termsEditable ? { terms } : {}),
      },
      ...(changed.length > 0 ? { fieldSources: Object.fromEntries(changed.map((field) => [field, source.trim()])) } : {}),
    });
  };

  return (
    <div data-proposal-correction="">
      <h2 className="mb-3">{t('console.queue.correct.title')}</h2>
      <p className="mb-3 text-meta text-muted">{t('console.queue.correct.hint')}</p>
      {Object.entries(summaries).map(([language, text]) => (
        <Field key={language} id={`correct-text-${language}`} label={`${t('console.queue.field.text', { language: languageName(language, ctx.locale) })}${language === payload.originalLanguage ? ` (${t('console.queue.detail.original')})` : ''}`}>
          <TextArea
            id={`correct-text-${language}`}
            lang={language}
            className="min-h-[120px]"
            value={text}
            onChange={(e) => setSummaries((prev) => ({ ...prev, [language]: e.target.value }))}
          />
        </Field>
      ))}
      {dateEditable ? (
        <Field id="correct-effective-from" label={t('console.queue.detail.effectiveDate')}>
          <TextInput id="correct-effective-from" type="date" value={effectiveFrom ?? ''} onChange={(e) => setEffectiveFrom(e.target.value)} />
        </Field>
      ) : null}
      {termsEditable ? (
        <Field id="correct-scope" label={t('console.queue.detail.scope')} hint={t('console.queue.correct.scopeHint')}>
          <ChipRow>
            {terms.map((ref) => (
              <Chip key={ref} pressed onClick={() => setTerms((prev) => prev.filter((r) => r !== ref))}>
                {labelOf(ref)} <span aria-hidden="true">{REMOVE_GLYPH}</span>
              </Chip>
            ))}
          </ChipRow>
          {addable.length > 0 ? (
            <Select
              id="correct-scope-add"
              className="mt-2 w-auto"
              value=""
              onChange={(e) => {
                if (e.target.value !== '') setTerms((prev) => [...prev, e.target.value]);
              }}
            >
              <option value="" />
              {addable.map((term) => (
                <option key={term.ref} value={term.ref}>
                  {term.label}
                </option>
              ))}
            </Select>
          ) : null}
        </Field>
      ) : null}
      {changed.length > 0 ? (
        <Field id="correct-source" label={t('console.queue.correct.source')} hint={t('console.queue.correct.sourceHint')}>
          <TextInput id="correct-source" value={source} onChange={(e) => setSource(e.target.value)} />
        </Field>
      ) : null}
      <Field id="correct-note" label={t('console.queue.correct.note')} hint={t('console.queue.correct.noteHint')}>
        <TextInput id="correct-note" value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {approve.isError ? <ProblemAlert error={approve.error} /> : null}
      <ButtonBar>
        <Button variant="danger" disabled={approve.isPending} onClick={() => setRejecting(true)}>
          {t('console.queue.reject')}
        </Button>
        <Button disabled={approve.isPending} onClick={submit}>
          {t('console.queue.approve')}
        </Button>
      </ButtonBar>
      <p className="mt-1.5 text-right text-meta text-muted">{t('console.queue.approveHint')}</p>
      <RejectProposalDialog proposalId={proposal.id} open={rejecting} onClose={() => setRejecting(false)} />
    </div>
  );
}
