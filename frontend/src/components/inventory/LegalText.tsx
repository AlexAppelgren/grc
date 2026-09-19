'use client';

import type { ReactNode } from 'react';

import { languageName } from '@/features/library/version-presentation';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';

// The legal text block (foundations.md "Legal text block";
// tenant-obligation.html, tenant-instrument.html). The block is an ordinary
// card; its brass margin is the product's signature: sand with the paragraph
// sign in Noto Sans Mono at display size and the reference under it, in
// brass. The text sits in its own language, long prose at 22px leading. A
// machine translation carries its label above the text, in the user's
// language and outside the text's lang; the original carries none (INV-05).
// On phones the margin becomes a strip above the text.

export interface LegalTextProps {
  /** The language the text is in, e.g. "sv". */
  lang: string;
  /** Set only for a machine translation: the language of the original. */
  translatedFrom?: string;
  /** Under the paragraph sign: the instrument and provision reference. */
  reference?: ReactNode;
  children: ReactNode;
}

export function LegalText({ lang, translatedFrom, reference, children }: LegalTextProps) {
  const t = useT();
  const locale = useLocale();
  return (
    <div data-legal-text="" className="grid overflow-hidden rounded-card border border-line bg-surface md:grid-cols-[96px_1fr]">
      <div data-legal-margin="" className="flex items-baseline gap-2.5 bg-sand px-4 py-2.5 text-brass md:block md:px-2.5 md:py-5 md:text-center">
        <span aria-hidden="true" className="font-mono text-display font-normal">
          {t('legal.sectionSign')}
        </span>
        {reference !== undefined ? <span className="font-mono text-meta md:mt-2 md:block">{reference}</span> : null}
      </div>
      <div className="max-w-[70ch] p-4 md:px-6 md:py-5">
        {translatedFrom !== undefined ? (
          <p data-machine-translation="" className="mb-2 text-meta font-medium text-brass">
            {t('legal.machineTranslation', { language: languageName(translatedFrom, locale) })}
          </p>
        ) : null}
        <div lang={lang} className="leading-[1.375rem]">
          {children}
        </div>
      </div>
    </div>
  );
}
