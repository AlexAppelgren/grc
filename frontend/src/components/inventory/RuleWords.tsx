'use client';

import Link from 'next/link';
import { useId, useLayoutEffect, useRef, useState } from 'react';

import { instrumentHref } from '@/components/inventory/ObligationPanels';
import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { Fold } from '@/components/ui/fold';
import { firstText, isLong, originalOf, provisionChipLabel, provisionPlace, provisionTextLabel } from '@/features/library/rule-words-presentation';
import type { ObligationDetail } from '@/features/library/types';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';
import { externalHref } from '@/shared/utils/external-href';

// "The rule's own words" (design/screens/tenant-obligation.html; INV-02,
// INV-05): the verbatim text of every provision the obligation cites, in the
// order the read gives them, under bleqq's plain-words summary. Each opens in
// the reader's language when the library holds it, else English, else the
// original, and says above the text what that text is. The text is the law's:
// its paragraph breaks and list lines are kept exactly as stored, and nothing
// reflows, trims or re-cases it. A provision whose wording the library does
// not hold yet says so in one line and points to the source.

type Provision = ObligationDetail['provisions'][number];

/** Two provisions open; the rest wait behind "Show <n> more". */
const SHOWN = 2;

function ProvisionWords({ provision, obligation }: { provision: Provision; obligation: ObligationDetail }) {
  const t = useT();
  const locale = useLocale();
  const textId = useId();
  const [chosen, setChosen] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const { texts } = provision;
  const shown = texts.find((text) => text.language === chosen) ?? firstText(texts, locale);
  const source = externalHref(obligation.provenance.sourceUrl);
  const clamped = shown !== null && isLong(shown.text) && !expanded;
  // Whether the clamped box really cuts the text: a long text on a tall screen
  // may fit, and then "Show all" would change nothing. Measured again when the
  // window, and with it the clamp's height, changes.
  const box = useRef<HTMLDivElement>(null);
  const [cut, setCut] = useState(false);
  const shownText = shown?.text;
  useLayoutEffect(() => {
    const element = box.current;
    if (!clamped || element === null) return undefined;
    const measure = () => setCut(element.scrollHeight > element.clientHeight);
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [clamped, shownText]);

  return (
    <article className="grid overflow-hidden rounded-card border border-line bg-surface md:grid-cols-[128px_1fr]" data-provision-words={provision.id}>
      <div className="flex items-baseline gap-2.5 bg-sand px-4 py-2.5 text-brass md:block md:px-2.5 md:py-5 md:text-center">
        <span aria-hidden="true" className="font-mono text-display font-normal">
          {t('legal.sectionSign')}
        </span>
        <span className="font-mono text-meta md:mt-2 md:block" data-provision-ref="">
          <Link href={instrumentHref(obligation.instrument.id)} prefetch={false} className="underline">
            {obligation.instrument.shortName}
          </Link>{' '}
          <span className="whitespace-nowrap">{provisionPlace(provision, obligation.instrument.shortName)}</span>
        </span>
      </div>
      <div className="min-w-0 max-w-[70ch] p-4 md:px-6 md:py-5">
        {provision.heading === null || provision.heading === '' ? null : (
          // The source's own heading, in the source's language; with no text held, the language is not known and is left out.
          <h3 className="mb-2" lang={originalOf(texts)?.language}>
            {provision.heading}
          </h3>
        )}
        {shown === null ? (
          <p className="text-meta text-muted" data-provision-not-held="">
            {t('inventory.obligation.ruleWordsNotHeld')}{' '}
            {source === null ? null : (
              <a href={source} target="_blank" rel="noopener noreferrer" className="underline">
                {obligation.provenance.sourceLabel}
              </a>
            )}
          </p>
        ) : (
          <>
            {texts.length > 1 ? (
              <div data-provision-languages="">
                <ChipRow className="mb-3">
                  {texts.map((text) => (
                    <Chip key={text.language} pressed={text.language === shown.language} onClick={() => setChosen(text.language)}>
                      {provisionChipLabel(text, locale, t)}
                    </Chip>
                  ))}
                </ChipRow>
              </div>
            ) : null}
            <p className="mb-2 text-meta font-medium text-brass" data-provision-label="">
              {provisionTextLabel(shown, texts, locale, t)}
            </p>
            <div
              ref={box}
              id={textId}
              lang={shown.language}
              className={cn(
                'leading-[1.375rem] whitespace-pre-wrap',
                clamped && 'max-h-[60vh] overflow-hidden',
                // A fade at the cut, so it reads as more to come rather than as the end.
                clamped && cut && '[mask-image:linear-gradient(to_bottom,black_75%,transparent)]',
              )}
              data-provision-text=""
            >
              {shown.text}
            </div>
            {isLong(shown.text) && (expanded || cut) ? (
              <Button variant="ghost" size="small" className="mt-2" aria-expanded={expanded} aria-controls={textId} onClick={() => setExpanded(!expanded)}>
                {expanded ? t('inventory.obligation.showLess') : t('inventory.obligation.showAll')}
              </Button>
            ) : null}
          </>
        )}
      </div>
    </article>
  );
}

/** Every cited provision, the first two open; none at all for an obligation that cites no provision. */
export function RuleWords({ obligation }: { obligation: ObligationDetail }) {
  const t = useT();
  const { provisions } = obligation;
  if (provisions.length === 0) return null;
  const rest = provisions.slice(SHOWN);
  return (
    <section className="mt-6" data-rule-words="">
      <h2 className="mb-2 microlabel text-muted">{t('inventory.obligation.ruleWordsTitle')}</h2>
      <div className="grid gap-3">
        {provisions.slice(0, SHOWN).map((provision) => (
          <ProvisionWords key={provision.id} provision={provision} obligation={obligation} />
        ))}
      </div>
      {rest.length === 0 ? null : (
        <Fold title={t('inventory.obligation.ruleWordsMore', { count: rest.length })} className="mt-3">
          <div className="grid gap-3">
            {rest.map((provision) => (
              <ProvisionWords key={provision.id} provision={provision} obligation={obligation} />
            ))}
          </div>
        </Fold>
      )}
    </section>
  );
}
