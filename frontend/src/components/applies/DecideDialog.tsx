'use client';

import { useState } from 'react';

import { Chip } from '@/components/ui/Chip';
import { FormDialog } from '@/components/ui/Dialogs';
import { TextArea } from '@/components/ui/Field';
import type { DecideAllBody } from '@/features/applies/api';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Does it apply to <company>?" (design/screens/tenant-applies.html): one dialog for every
// way in, everything to decide, one regulation, the ticked rows, and later one obligation.
// It knows what it covers only as the words and the count it is given, never where its
// targets came from. Applies is chosen when it opens, with the reason suggested from the
// licence facts; Does not apply starts empty, because the fact that takes a company outside
// a rule is the person's to give. One confirming button that says what it does, and no
// second step.

export type Answer = DecideAllBody['applicability'];

/** The reason a decision may carry at most (the API's own limit). */
const REASON_MAX = 2000;

export interface DecideDialogProps {
  /** The company's name, as the title asks about it. */
  company: string;
  /** What the decision covers, in words: "41 obligations in 6 regulations". */
  covers: string;
  /** How many obligations it sets, as the button says. */
  count: number;
  /** The reason suggested from the licence facts, offered with Applies. */
  suggestion: string;
  pending: boolean;
  /** The refused start, shown above the buttons; leave it out when there is none. */
  error?: unknown;
  codes?: Readonly<Record<string, string>>;
  onSubmit: (decision: { applicability: Answer; reason: string }) => void;
  onClose: () => void;
}

export function DecideDialog({ company, covers, count, suggestion, pending, error, codes, onSubmit, onClose }: DecideDialogProps) {
  const t = useT();
  const [answer, setAnswer] = useState<Answer>('applies');
  const [reason, setReason] = useState(suggestion);
  // The person's own words, which a change of answer never replaces.
  const [typed, setTyped] = useState(false);
  const choose = (next: Answer) => {
    setAnswer(next);
    if (typed && reason.trim() !== '') return;
    setTyped(false);
    setReason(next === 'applies' ? suggestion : '');
  };
  const suggested = answer === 'applies' && !typed;
  const trimmed = reason.trim();
  return (
    <FormDialog
      title={t('applies.dialog.title', { company })}
      description={covers}
      submitLabel={t(answer === 'applies' ? 'applies.dialog.setApplies' : 'applies.dialog.setNotApplicable', { count })}
      submitDisabled={trimmed === ''}
      pending={pending}
      error={error}
      codes={codes}
      onSubmit={() => onSubmit({ applicability: answer, reason: trimmed })}
      onClose={onClose}
      formProps={{ 'data-decide-dialog': '' }}
    >
      <div className="mb-3 grid gap-1.5">
        <span id="decide-decision" className="font-medium">
          {t('applies.dialog.decision')}
        </span>
        <div role="group" aria-labelledby="decide-decision" className="flex flex-wrap gap-2">
          <Chip pressed={answer === 'applies'} onClick={() => choose('applies')}>
            {t('obligationApplicability.applies')}
          </Chip>
          <Chip pressed={answer === 'not_applicable'} onClick={() => choose('not_applicable')}>
            {t('obligationApplicability.notApplicable')}
          </Chip>
        </div>
      </div>
      <div className="mb-3 grid gap-1.5">
        <label htmlFor="decide-reason" className="font-medium">
          {t('applies.dialog.reason')}
        </label>
        {suggested ? (
          <span id="decide-reason-suggested" className="microlabel text-muted" data-suggested="">
            {t('applies.dialog.suggested')}
          </span>
        ) : null}
        <TextArea
          id="decide-reason"
          value={reason}
          maxLength={REASON_MAX}
          placeholder={t('applies.dialog.reasonPlaceholder')}
          aria-describedby={suggested ? 'decide-reason-suggested' : undefined}
          onChange={(event) => {
            setReason(event.target.value);
            setTyped(true);
          }}
        />
      </div>
      <p className="text-meta text-muted">{t('applies.dialog.audit')}</p>
      <p className="text-meta text-muted">{t('applies.dialog.colleagues')}</p>
    </FormDialog>
  );
}
