'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Chip, ChipRow } from '@/components/ui/Chip';
import { LegalText, RuleText } from '@/components/inventory/LegalText';
import { diffSentence } from '@/components/inventory/ObligationScreen';
import { Notice } from '@/components/ui/Notice';
import { Meta, Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useInstrumentProvisions, useProvisionDiff } from '@/features/library/hooks';
import { STANDARD_LEVEL_KIND } from '@/features/library/obligation-presentation';
import { chosenText } from '@/features/library/rule-words-presentation';
import type { ProvisionNode } from '@/features/library/types';
import { inForceLabel } from '@/features/library/version-presentation';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { externalHref } from '@/shared/utils/external-href';
import { problemStatus } from '@/shared/utils/problem';

// The provision tree, on the instrument card (design/screens/tenant-instrument.html;
// INV-02, INV-04, INV-05). A disclosure list: every version a unit has ever
// carried stays on its own chip, so choosing one never depends on today's
// date, and "Show what changed" opens the sentence-level diff between two of
// them. A unit with no version of its own still shows its children.
//
// Each version's text is the rule's own words, drawn as the obligation page
// draws a cited provision (RuleText, D-142): every language the version
// holds on a chip of its own, the reader's language first when it is held,
// else English, else the original, under the line that is always true of
// it. The language chosen stays across versions where the version holds it.
// "Show what changed" is taken in the language shown, labelled the same way,
// and names the two versions it compares, which are the latest and the one
// before it whichever chip is pressed. A version that holds no text says so,
// and shows no comparison: with no text of its own there is no language to
// take one in and no original to label it against.
//
// A standard's text is licensed (D-37): the library holds no provision under
// it, so the panel says so and links the publisher's catalogue instead of
// reading a tree, and a reader without library.read sees why the tree is
// missing rather than an error to retry.

/** The version a node opens on: the one in force on the read's date, or its first version when none is in force. */
export function defaultVersion(node: ProvisionNode): number | null {
  if (node.inForceVersion !== null) return node.inForceVersion;
  return node.versions[0]?.versionNumber ?? null;
}

function ProvisionUnit({ node }: { node: ProvisionNode }) {
  const t = useT();
  const ctx = useFormatContext();
  const locale = useLocale();
  const [selected, setSelected] = useState<number | null>(defaultVersion(node));
  const [chosen, setChosen] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const version = node.versions.find((row) => row.versionNumber === selected);
  const texts = version?.texts ?? [];
  const shown = chosenText(texts, chosen, locale);
  // The comparison is taken in the language shown, so a chip changes both.
  const comparing = showDiff && shown !== null;
  const diff = useProvisionDiff(node.id, shown?.language ?? locale, comparing);
  const compared = comparing ? diff.data : undefined;

  return (
    <li>
      <details open data-provision={node.stableKey}>
        <summary className="cursor-pointer py-1.5 font-medium">
          <span className="mr-1.5 font-mono text-meta text-muted">{node.refLabel}</span>
          {node.heading}
        </summary>
        <div className="py-2">
          {version === undefined ? null : (
            <>
              <ChipRow className="mb-2">
                {node.versions.map((row) => (
                  <Chip key={row.versionNumber} pressed={row.versionNumber === selected} onClick={() => setSelected(row.versionNumber)}>
                    {inForceLabel(row.effectiveFrom, row.effectiveTo, t, ctx)}
                  </Chip>
                ))}
                {node.versions.length > 1 ? (
                  <Chip pressed={showDiff} onClick={() => setShowDiff((current) => !current)}>
                    {t('inventory.obligation.showWhatChanged')}
                  </Chip>
                ) : null}
              </ChipRow>

              {comparing && diff.isError ? <ErrorState title={t('inventory.obligation.diffErrorTitle')} onRetry={() => void diff.refetch()} /> : null}
              {compared === undefined ? null : <Notice data-diff-banner="">{diffSentence(compared, t, ctx)}</Notice>}
              {shown === null ? (
                <p className="text-meta text-muted" data-provision-not-held="">
                  {t('inventory.obligation.ruleWordsNotHeld')}
                </p>
              ) : (
                <LegalText reference={node.refLabel}>
                  <RuleText texts={texts} shown={shown} onChoose={setChosen} diff={compared} />
                </LegalText>
              )}
              {compared !== undefined || version.transitionalNote === '' ? null : (
                <p className="mt-2 text-meta text-muted" data-transitional-note="">
                  {version.transitionalNote}
                </p>
              )}
            </>
          )}

          {node.obligations.length === 0 ? null : (
            <Meta className="mt-2" data-provision-obligations="">
              {node.obligations.map((obligation) => (
                <Link key={obligation.id} href={`/inventory/obligations/${obligation.id}`} prefetch={false} className="underline">
                  {obligation.title === null ? obligation.refLabel : obligation.title.text}
                </Link>
              ))}
            </Meta>
          )}
        </div>
        {node.children.length === 0 ? null : (
          <ul className="m-0 list-none border-l border-line pl-4">
            {node.children.map((child) => (
              <ProvisionUnit key={child.id} node={child} />
            ))}
          </ul>
        )}
      </details>
    </li>
  );
}

/**
 * A standard's text is licensed, so the library holds no provision under it
 * and the tree is never read: the panel says so and links the publisher's
 * catalogue entry, the instrument's own source.
 */
function LicensedText({ sourceUrl }: { sourceUrl: string }) {
  const t = useT();
  const href = externalHref(sourceUrl);
  return (
    <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-provisions-licensed="">
      <h2 className="text-fg">{t('inventory.instrument.provisionsLicensed.title')}</h2>
      <p className="mx-auto mt-2 max-w-[60ch]">{t('inventory.instrument.provisionsLicensed.body')}</p>
      {href === null ? (
        <p className="mt-3 break-all text-fg">{sourceUrl}</p>
      ) : (
        <a href={href} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block font-medium text-fg underline">
          {t('inventory.instrument.provisionsLicensed.link')}
        </a>
      )}
    </div>
  );
}

function ProvisionNodes({ instrumentId }: { instrumentId: string }) {
  const t = useT();
  const provisions = useInstrumentProvisions(instrumentId);
  const nodes = provisions.data ?? [];
  // No provision text held: the panel is left out rather than promising text that may never come.
  if (provisions.isSuccess && nodes.length === 0) return null;

  return (
    <Panel title={t('inventory.instrument.provisionsTitle')} data-provision-tree="">
      {provisions.isPending ? (
        <LoadingState rows={2} />
      ) : provisions.isError ? (
        problemStatus(provisions.error) === 403 ? (
          <div data-provisions-denied="">
            <ProblemAlert error={provisions.error} />
          </div>
        ) : (
          <ErrorState title={t('inventory.instrument.provisionsErrorTitle')} onRetry={() => void provisions.refetch()} />
        )
      ) : (
        <ul className="m-0 list-none p-0">
          {nodes.map((node) => (
            <ProvisionUnit key={node.id} node={node} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** The instrument's level kind and source decide whether there is a tree to read at all. */
export function ProvisionTree({ instrumentId, levelKind, sourceUrl }: { instrumentId: string; levelKind: string | null; sourceUrl: string }) {
  const t = useT();
  if (levelKind !== STANDARD_LEVEL_KIND) return <ProvisionNodes instrumentId={instrumentId} />;
  return (
    <Panel title={t('inventory.instrument.provisionsTitle')} data-provision-tree="">
      <LicensedText sourceUrl={sourceUrl} />
    </Panel>
  );
}
