import { DiffText, type DiffSegment } from '@/components/inventory/DiffText';
import { LegalText } from '@/components/inventory/LegalText';
import { Pill } from '@/components/ui/Pill';
import { createT, defaultLocale, type MessageKey } from '@/shared/i18n';

const t = createT(defaultLocale);

const DIFF: readonly (readonly [DiffSegment['op'], MessageKey])[] = [
  ['equal', 'public.record.kept1'],
  ['delete', 'public.record.removed'],
  ['insert', 'public.record.added'],
  ['equal', 'public.record.kept2'],
];

const CHAIN: readonly MessageKey[] = ['public.record.sighted', 'public.record.confirmed', 'public.record.applied'];

// The change record on the public page, drawn with the product's own parts:
// the pills, the legal text block, the sentence diff and the "So what?"
// callout. It is sample content from the prototype's data and says so. The
// pills follow a change header's slot order and tones (pills-and-labels.md):
// the change type in `notice`, then the urgency, "within 3 months" in
// `warning`; the authority and instrument are plain meta text.
export function SampleRecord() {
  return (
    <article aria-labelledby="public-record-title" className="rounded-card border border-line bg-surface p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="microlabel text-muted">{t('public.record.label')}</span>
        <span className="font-mono text-meta text-muted">{t('public.record.sample')}</span>
      </div>
      <div className="mb-2.5 flex flex-wrap gap-1.5">
        <Pill tone="notice">{t('public.record.changeType')}</Pill>
        <Pill tone="warning">{t('public.record.urgency')}</Pill>
      </div>
      <h3 id="public-record-title" className="mb-1 text-title">
        {t('public.record.title')}
      </h3>
      <p className="mb-3.5 text-meta text-muted">{t('public.record.meta')}</p>
      <LegalText lang={defaultLocale}>
        <DiffText segments={DIFF.map(([op, key]) => ({ op, text: t(key) }))} />
      </LegalText>
      <div className="mt-3 rounded-card bg-sand px-3.5 py-3">
        <span className="block text-meta font-semibold text-brass">{t('watch.soWhat.aiDraft')}</span>
        <p className="max-w-[70ch]">
          <span className="font-semibold">{t('watch.soWhat.label')}</span> <span>{t('public.record.soWhat')}</span>
        </p>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-3.5 gap-y-1.5 border-t border-line pt-3 font-mono text-meta text-muted">
        {CHAIN.map((key) => (
          <li key={key}>{t(key)}</li>
        ))}
      </ul>
    </article>
  );
}
