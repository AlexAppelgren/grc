import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, TextArea } from '@/components/ui/Field';
import { ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import type { ChangeDetail } from '@/features/watch/api';
import { useCanWorkCase, useConfirmSoWhat, useSaveSoWhat } from '@/features/watch/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// The "So what?" block of design/screens/tenant-change.html (WAT-05, CAS-01).
//
// The wording is machine output until a person here stands behind it, and
// this block is where a reader meets that distinction, so it is drawn as a
// draft with its provenance and never as the bank's settled view: the label
// says the words are a draft nobody has confirmed, and the line under them
// names the agent that wrote them. D-66: the agent that read the change
// drafts the "So what?" in the same run, so the provenance is the model it
// reported, not a second call of ours.
//
// The draft is written once per change from library facts only and copied
// unconfirmed into each bank's case (D-07, D-32), so what is shown is this
// bank's own copy where it has one; another bank's copy is never here.
//
// A person holding `cases.work` settles it for this bank alone: "Confirm
// wording" stands behind the draft as it is, and "Rewrite" replaces it with
// the bank's own words, which confirms them too. Both write this bank's case
// and no library row. Everyone else sees the label and no buttons. Neither
// route takes `If-Match` in R1 (the case carries no version until chunk 9),
// so the last save wins and there is no stale-write state to show.

export interface SoWhat {
  /** This bank's copy where it has a case, the library's draft otherwise. Null before an agent has read the change. */
  wording: string | null;
  confirmed: boolean;
  confirmedAt: string | null;
  /** The model the drafting agent reported, or null when a person registered the change. */
  agent: string | null;
}

export function soWhatOf(change: ChangeDetail): SoWhat {
  const text = change.case === null ? change.soWhatDraft : change.case.soWhatText;
  return {
    wording: text === null || text === '' ? null : text,
    confirmed: change.case?.soWhatConfirmed ?? false,
    confirmedAt: change.case?.soWhatConfirmedAt ?? null,
    agent: change.model,
  };
}

/**
 * Where the words came from, or when a person here stood behind them. Once
 * confirmed, only the confirmation is named (the card's confirmed state): a
 * rewritten wording is the bank's own, and naming the agent as its drafter
 * would credit a model with words it never wrote. The draft's provenance
 * stays in the AI output log.
 */
export function soWhatProvenance(soWhat: SoWhat, t: Translate, ctx: FormatContext): string[] {
  if (soWhat.confirmed && soWhat.confirmedAt !== null) return [t('watch.soWhat.confirmedAt', { date: formatDate(soWhat.confirmedAt, ctx) })];
  return [soWhat.agent === null ? t('watch.soWhat.draftedByAgent') : t('watch.soWhat.draftedBy', { agent: soWhat.agent })];
}

export function SoWhatPanel({ change }: { change: ChangeDetail }) {
  const t = useT();
  const ctx = useFormatContext();
  const canWork = useCanWorkCase(change);
  const confirm = useConfirmSoWhat(change.id);
  const [rewriting, setRewriting] = useState(false);
  const soWhat = soWhatOf(change);

  if (rewriting) return <SoWhatRewrite changeId={change.id} wording={soWhat.wording ?? ''} onClose={() => setRewriting(false)} />;
  if (soWhat.wording === null) return <EmptyState title={t('watch.soWhat.emptyTitle')} body={t('watch.soWhat.emptyBody')} />;
  return (
    <div className="my-3.5 rounded-card bg-sand px-3.5 py-3" data-so-what="" data-so-what-confirmed={soWhat.confirmed ? '' : undefined}>
      {/* The label goes only when a person here has confirmed the wording, which is
          the one thing that turns machine output into this bank's own position. */}
      {soWhat.confirmed ? null : <span className="block text-meta font-semibold text-brass">{t('watch.soWhat.aiDraft')}</span>}
      <p className="mb-1 max-w-[70ch]">
        <span className="font-semibold">{t('watch.soWhat.label')}</span> <span data-so-what-text="">{soWhat.wording}</span>
      </p>
      <p className="flex flex-wrap gap-x-2.5 gap-y-1 text-meta text-muted">
        {soWhatProvenance(soWhat, t, ctx).map((line, index) => (
          // Two lines can read the same, so the position is the key.
          <span key={index}>{line}</span>
        ))}
      </p>
      {canWork ? (
        <>
          {confirm.isError ? <ProblemAlert error={confirm.error} /> : null}
          <ButtonBar className="mt-2.5">
            <Button variant="ghost" size="small" disabled={confirm.isPending} onClick={() => setRewriting(true)}>
              {t('watch.soWhat.rewrite')}
            </Button>
            {soWhat.confirmed ? null : (
              <Button size="small" disabled={confirm.isPending} onClick={() => confirm.mutate()}>
                {t('watch.soWhat.confirm')}
              </Button>
            )}
          </ButtonBar>
        </>
      ) : null}
    </div>
  );
}

/** The card's "Rewrite the So what" state: this bank's own words, for this bank only. */
function SoWhatRewrite({ changeId, wording, onClose }: { changeId: string; wording: string; onClose: () => void }) {
  const t = useT();
  const save = useSaveSoWhat(changeId);
  const [text, setText] = useState(wording);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    // The hook re-reads the change before this closes, so the panel never
    // shows the old wording under the new confirmation.
    save.mutate(text.trim(), { onSuccess: onClose });
  };

  return (
    <form className="my-3.5" onSubmit={submit} noValidate aria-busy={save.isPending} data-so-what-rewrite="">
      <Field id="so-what-text" label={t('watch.soWhat.label')} hint={t('watch.soWhat.editHint')}>
        <TextArea id="so-what-text" value={text} aria-describedby="so-what-text-hint" onChange={(event) => setText(event.target.value)} />
      </Field>
      {save.isError ? <ProblemAlert error={save.error} /> : null}
      <ButtonBar>
        <Button variant="ghost" disabled={save.isPending} onClick={onClose}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={text.trim() === '' || save.isPending}>
          {t('watch.soWhat.save')}
        </Button>
      </ButtonBar>
    </form>
  );
}
