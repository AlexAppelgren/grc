'use client';

import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';

import { DiffText } from '@/components/inventory/DiffText';
import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { diffFlags, isLong, provisionChipLabel, provisionTextLabel } from '@/features/library/rule-words-presentation';
import type { LocalizedText, VersionDiff } from '@/features/library/types';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// The rule's own words (foundations.md "Legal text block"; tenant-obligation.html,
// tenant-instrument.html; INV-02, INV-05, D-142). Two parts, shared by the obligation
// page's cited provisions (RuleWords) and the regulation page's provision tree.
//
// LegalText is the block: an ordinary card whose brass margin is the product's
// signature, sand with the paragraph sign in Noto Sans Mono at display size and the
// reference under it. On phones the margin becomes a strip above the text.
//
// RuleText is what sits in it: a chip per language the provision holds when it holds
// more than one, the line that is always true of the text shown (the original, a
// machine translation of it, or the authority's own text in a second language), in the
// reader's language and outside the text's own, and the text itself, in its language at
// 22px leading, its paragraph breaks and list lines kept exactly as stored. A text
// longer than about a screen opens clamped with "Show all". A comparison of two versions
// takes the text's place, labelled for the language it was taken in.

export function LegalText({ reference, children }: { reference?: ReactNode; children: ReactNode }) {
  const t = useT();
  return (
    <div data-legal-text="" className="grid overflow-hidden rounded-card border border-line bg-surface md:grid-cols-[96px_1fr]">
      <div data-legal-margin="" className="flex items-baseline gap-2.5 bg-sand px-4 py-2.5 text-brass md:block md:px-2.5 md:py-5 md:text-center">
        <span aria-hidden="true" className="font-mono text-display font-normal">
          {t('legal.sectionSign')}
        </span>
        {reference !== undefined ? <span className="font-mono text-meta md:mt-2 md:block">{reference}</span> : null}
      </div>
      <div className="min-w-0 max-w-[70ch] p-4 md:px-6 md:py-5">{children}</div>
    </div>
  );
}

export interface RuleTextProps {
  /** Every language the provision holds, the original first. */
  texts: readonly LocalizedText[];
  /** The one shown: the reader's choice, else the one it opens in. */
  shown: LocalizedText;
  onChoose: (language: string) => void;
  /** Shown in place of the text: what changed between two versions, in the language it was taken in. */
  diff?: VersionDiff;
}

export function RuleText({ texts, shown, onChoose, diff }: RuleTextProps) {
  const t = useT();
  const locale = useLocale();
  const textId = useId();
  const [expanded, setExpanded] = useState(false);
  const clamped = isLong(shown.text) && !expanded;
  // Whether the clamped box really cuts the text: a long text on a tall screen
  // may fit, and then "Show all" would change nothing. Measured again when the
  // window, and with it the clamp's height, changes.
  const box = useRef<HTMLDivElement>(null);
  const [cut, setCut] = useState(false);
  useLayoutEffect(() => {
    const element = box.current;
    if (!clamped || element === null) return undefined;
    const measure = () => setCut(element.scrollHeight > element.clientHeight);
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [clamped, shown.text, diff]);

  return (
    <>
      {texts.length > 1 ? (
        <div data-provision-languages="">
          <ChipRow className="mb-3">
            {texts.map((text) => (
              <Chip key={text.language} pressed={text.language === shown.language} onClick={() => onChoose(text.language)}>
                {provisionChipLabel(text, locale, t)}
              </Chip>
            ))}
          </ChipRow>
        </div>
      ) : null}
      <p className="mb-2 text-meta font-medium text-brass" data-provision-label="">
        {provisionTextLabel(diff === undefined ? shown : diffFlags(diff, texts), texts, locale, t)}
      </p>
      <div
        ref={box}
        id={textId}
        lang={diff === undefined ? shown.language : diff.language}
        className={cn(
          'leading-[1.375rem] whitespace-pre-wrap',
          clamped && 'max-h-[60vh] overflow-hidden',
          // A fade at the cut, so it reads as more to come rather than as the end.
          clamped && cut && '[mask-image:linear-gradient(to_bottom,black_75%,transparent)]',
        )}
        data-provision-text=""
      >
        {diff === undefined ? shown.text : <DiffText segments={diff.segments} />}
      </div>
      {isLong(shown.text) && (expanded || cut) ? (
        <Button variant="ghost" size="small" className="mt-2" aria-expanded={expanded} aria-controls={textId} onClick={() => setExpanded(!expanded)}>
          {expanded ? t('inventory.obligation.showLess') : t('inventory.obligation.showAll')}
        </Button>
      ) : null}
    </>
  );
}
