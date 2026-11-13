'use client';

import { useState } from 'react';

import { AiLabel } from '@/components/ui/AiLabel';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { FormDialog } from '@/components/ui/Dialogs';
import { TextArea } from '@/components/ui/Field';
import { ProblemAlert } from '@/components/ui/States';
import type { DecideAllBody, ReasonDraftScope } from '@/features/applies/api';
import { useDraftReason } from '@/features/applies/hooks';
import { presentApplicability } from '@/features/register/register-presentation';
import type { Applicability } from '@/features/register/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';

// "Does it apply to <company>?" (design/screens/tenant-applies.html, tenant-obligation.html;
// D-141): one dialog for every way in, everything to decide, one regulation, the ticked rows,
// and one obligation on its own page. It knows what it covers only as the words and the
// count it is given, never where its targets came from. A row nobody answered opens on
// Applies, with the reason suggested from the licence facts; Does not apply starts empty,
// because the fact that takes a company outside a rule is the person's to give. One
// obligation already answered opens on its answer and its stored reason. One confirming
// button that says what it does, and no second step.
//
// "Draft with AI" (D-143, ADR 0069) asks a model for the reason from the licence facts and
// the library's facts, which the server reads itself: nothing typed here is sent. The draft
// is labelled as AI until the person edits it or sets the answer, and its id goes with the
// answer so the AI log records that they confirmed or edited it. It is offered only to a
// holder of applicability.approve, and only where a company is named.

export type Answer = DecideAllBody['applicability'];

/** One obligation's stored answer, which the dialog opens on. */
export interface Current {
  applicability: Applicability;
  reason: string | null;
}

/** The reason a decision may carry at most (the API's own limit). */
const REASON_MAX = 2000;
const APPROVE_PERMISSION = 'applicability.approve';

interface Decision<A extends Applicability> {
  applicability: A;
  reason: string;
  /** The AI draft the reason began from, when it did. */
  reasonDraftId?: string;
}

export type DecideDialogProps = {
  /** The company's name, as the title asks about it; null for the obligation as a whole: "Does it apply to us?". */
  company: string | null;
  /** What the decision covers, in words: "41 obligations in 6 regulations". */
  covers?: string;
  /** How many obligations it sets, as the button says ("Set 41 to Applies"); left out for one obligation ("Set to Applies"). */
  count?: number;
  /** One obligation's answer, null while nobody has given one; it shows as "Now: …". Left out for many. */
  current?: Current | null;
  /** The reason suggested from the licence facts, offered with Applies on a row nobody answered; it may arrive after the dialog opened. */
  suggestion: string;
  /** What an AI draft of the reason is for: the company and the filter. Left out where no company is named, and no draft is offered. */
  draftScope?: ReasonDraftScope;
  pending: boolean;
  /** The refused write, shown above the buttons; leave it out when there is none. */
  error?: unknown;
  codes?: Readonly<Record<string, string>>;
  onClose: () => void;
} & (
  | { /** "Not assessed" is a third choice only where the answer accepts it: one obligation's, never a run's. */ notAssessed?: false; onSubmit: (decision: Decision<Answer>) => void }
  | { notAssessed: true; onSubmit: (decision: Decision<Applicability>) => void }
);

export function DecideDialog(props: DecideDialogProps) {
  const { company, covers, count, current, suggestion, draftScope, pending, error, codes, onClose } = props;
  const t = useT();
  const permissions = usePermissions() ?? [];
  const canDraft = draftScope !== undefined && permissions.includes(APPROVE_PERMISSION);
  const drafting = useDraftReason();
  // The AI draft put in the field, kept until a change of answer replaces it or the field is emptied.
  const [aiDraft, setAiDraft] = useState<{ id: string; text: string } | null>(null);
  // A row stored as "Not assessed" decides nothing yet: it opens on Applies, as one nobody answered.
  const stored = current !== undefined && current !== null && current.applicability !== 'under_assessment' ? current.applicability : null;
  // What the field holds for an answer while the person has typed nothing of their own: the
  // stored reason beside the stored answer, the suggestion beside Applies, else nothing,
  // so a reason never goes with an answer it was not given for.
  const filled = (next: Applicability): string =>
    current !== undefined && current !== null && next === current.applicability ? (current.reason ?? '') : next === 'applies' ? suggestion : '';
  const [answer, setAnswer] = useState<Applicability>(stored ?? 'applies');
  const [reason, setReason] = useState(filled(stored ?? 'applies'));
  // Only the person's own words in this dialog, which a change of answer never replaces.
  const [typed, setTyped] = useState(false);
  const showsStored = current !== undefined && current !== null && answer === current.applicability;
  // A suggestion that arrives while the field still holds none of the person's own words is put in.
  const [offered, setOffered] = useState(suggestion);
  if (offered !== suggestion) {
    setOffered(suggestion);
    if (!typed && answer === 'applies' && !showsStored && aiDraft === null) setReason(suggestion);
  }
  const choose = (next: Applicability) => {
    setAnswer(next);
    if (typed && reason.trim() !== '') return;
    setTyped(false);
    setAiDraft(null);
    setReason(filled(next));
  };
  const draft = () => {
    if (draftScope === undefined) return;
    drafting.mutate(
      { ...draftScope, applicability: answer },
      {
        onSuccess: (drafted) => {
          setReason(drafted.text);
          setTyped(false);
          setAiDraft({ id: drafted.generationId, text: drafted.text });
        },
      },
    );
  };
  const aiLabelled = aiDraft !== null && reason === aiDraft.text;
  const suggested = answer === 'applies' && !typed && !showsStored && suggestion !== '' && aiDraft === null;
  const trimmed = reason.trim();
  const label = presentApplicability(answer, t).label;
  const drafted = aiDraft === null ? {} : { reasonDraftId: aiDraft.id };
  const submit = () => {
    if (props.notAssessed === true) props.onSubmit({ applicability: answer, reason: trimmed, ...drafted });
    else if (answer !== 'under_assessment') props.onSubmit({ applicability: answer, reason: trimmed, ...drafted });
  };
  const describedBy = aiLabelled ? 'decide-reason-ai' : suggested ? 'decide-reason-suggested' : undefined;
  const choices: readonly Applicability[] = props.notAssessed === true ? ['applies', 'not_applicable', 'under_assessment'] : ['applies', 'not_applicable'];
  return (
    <FormDialog
      title={company === null ? t('obligationApplicability.heading') : t('applies.dialog.title', { company })}
      description={covers}
      submitLabel={count === undefined ? t('applies.dialog.setOne', { answer: label }) : t('applies.dialog.set', { count, answer: label })}
      submitDisabled={trimmed === ''}
      pending={pending}
      error={error}
      codes={codes}
      onSubmit={submit}
      onClose={onClose}
      formProps={{ 'data-decide-dialog': '' }}
    >
      <div className="mb-3 grid gap-1.5">
        <span id="decide-decision" className="font-medium">
          {t('applies.dialog.decision')}
        </span>
        <div role="group" aria-labelledby="decide-decision" className="flex flex-wrap gap-2">
          {choices.map((choice) => (
            <Chip key={choice} pressed={answer === choice} onClick={() => choose(choice)}>
              {presentApplicability(choice, t).label}
            </Chip>
          ))}
        </div>
      </div>
      <div className="mb-3 grid gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="decide-reason" className="font-medium">
            {t('applies.dialog.reason')}
          </label>
          {canDraft ? (
            <Button variant="ghost" size="small" disabled={drafting.isPending || pending} aria-busy={drafting.isPending} onClick={draft} data-draft-reason="">
              {drafting.isPending ? t('applies.dialog.drafting') : t('applies.dialog.draft')}
            </Button>
          ) : null}
        </div>
        {aiLabelled ? <AiLabel id="decide-reason-ai" text={t('applies.dialog.aiDraft')} /> : null}
        {suggested ? (
          <span id="decide-reason-suggested" className="microlabel text-muted" data-suggested="">
            {t('applies.dialog.suggested')}
          </span>
        ) : null}
        <TextArea
          id="decide-reason"
          value={reason}
          maxLength={REASON_MAX}
          placeholder={answer === 'not_applicable' ? t('applies.dialog.reasonPlaceholder') : undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            setReason(event.target.value);
            setTyped(true);
            // Emptied, the reason no longer began as the draft.
            if (event.target.value.trim() === '') setAiDraft(null);
          }}
        />
        {drafting.isError ? (
          <ProblemAlert
            error={drafting.error}
            codes={{
              feature_off: t('applies.dialog.draftOff'),
              draft_refused: t('applies.dialog.draftRefused'),
              model_unavailable: t('applies.dialog.draftUnavailable'),
              not_found: t('applies.dialog.notFound'),
            }}
          />
        ) : null}
      </div>
      {current === undefined ? (
        <>
          <p className="text-meta text-muted">{t('applies.dialog.audit')}</p>
          <p className="text-meta text-muted">{t('applies.dialog.colleagues')}</p>
        </>
      ) : (
        <p className="text-meta text-muted" data-decide-now="">
          {current === null ? t('applies.dialog.nowToDecide') : t('applies.dialog.now', { answer: presentApplicability(current.applicability, t).label })}
        </p>
      )}
    </FormDialog>
  );
}
