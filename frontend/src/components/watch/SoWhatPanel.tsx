import { EmptyState } from '@/components/ui/EmptyState';
import { useFormatContext } from '@/features/identity/hooks';
import type { ChangeDetail } from '@/features/watch/api';
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

/** Where the words came from, and when a person here stood behind them. */
export function soWhatProvenance(soWhat: SoWhat, t: Translate, ctx: FormatContext): string[] {
  const lines = [soWhat.agent === null ? t('watch.soWhat.draftedByAgent') : t('watch.soWhat.draftedBy', { agent: soWhat.agent })];
  if (soWhat.confirmed && soWhat.confirmedAt !== null) lines.push(t('watch.soWhat.confirmedAt', { date: formatDate(soWhat.confirmedAt, ctx) }));
  return lines;
}

export function SoWhatPanel({ change }: { change: ChangeDetail }) {
  const t = useT();
  const ctx = useFormatContext();
  const soWhat = soWhatOf(change);
  if (soWhat.wording === null) return <EmptyState title={t('watch.soWhat.emptyTitle')} body={t('watch.soWhat.emptyBody')} />;
  return (
    <div className="my-3.5 rounded-card bg-sand px-3.5 py-3" data-so-what="" data-so-what-confirmed={soWhat.confirmed ? '' : undefined}>
      {/* The label goes only when a person here has confirmed the wording, which is
          the one thing that turns machine output into this bank's own position. */}
      {soWhat.confirmed ? null : <span className="block text-meta font-semibold text-brass">{t('watch.soWhat.aiDraft')}</span>}
      <p className="mb-1 max-w-[70ch]">
        <span className="font-semibold">{t('watch.soWhat.label')}</span> <span>{soWhat.wording}</span>
      </p>
      <p className="flex flex-wrap gap-x-2.5 gap-y-1 text-meta text-muted">
        {soWhatProvenance(soWhat, t, ctx).map((line, index) => (
          // Two lines can read the same, so the position is the key.
          <span key={index}>{line}</span>
        ))}
      </p>
    </div>
  );
}
