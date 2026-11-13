'use client';

import Link from 'next/link';
import { useState } from 'react';

import { RuleText } from '@/components/inventory/LegalText';
import { instrumentHref } from '@/components/inventory/ObligationPanels';
import { Fold } from '@/components/ui/fold';
import { chosenText, originalOf, provisionPlace } from '@/features/library/rule-words-presentation';
import type { ObligationDetail } from '@/features/library/types';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { externalHref } from '@/shared/utils/external-href';

// "The rule's own words" (design/screens/tenant-obligation.html; INV-02,
// INV-05): the verbatim text of every provision the obligation cites, in the
// order the read gives them, under bleqq's plain-words summary. Each opens in
// the reader's language when the library holds it, else English, else the
// original, and says above the text what that text is (RuleText in LegalText.tsx,
// shared with the regulation page's provision tree). The text is the law's:
// its paragraph breaks and list lines are kept exactly as stored, and nothing
// reflows, trims or re-cases it. A provision whose wording the library does
// not hold yet says so in one line and points to the source.

type Provision = ObligationDetail['provisions'][number];

/** Two provisions open; the rest wait behind "Show <n> more". */
const SHOWN = 2;

function ProvisionWords({ provision, obligation }: { provision: Provision; obligation: ObligationDetail }) {
  const t = useT();
  const locale = useLocale();
  const [chosen, setChosen] = useState<string | null>(null);
  const { texts } = provision;
  const shown = chosenText(texts, chosen, locale);
  const source = externalHref(obligation.provenance.sourceUrl);

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
          <RuleText texts={texts} shown={shown} onChoose={setChosen} />
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
