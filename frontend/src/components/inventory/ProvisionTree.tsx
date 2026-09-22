'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Chip, ChipRow } from '@/components/ui/Chip';
import { DiffText } from '@/components/inventory/DiffText';
import { EmptyState } from '@/components/ui/EmptyState';
import { LegalText } from '@/components/inventory/LegalText';
import { Meta, Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useInstrumentProvisions, useProvisionDiff } from '@/features/library/hooks';
import type { ProvisionNode } from '@/features/library/types';
import { inForceLabel } from '@/features/library/version-presentation';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';

// The provision tree, on the instrument card (design/screens/tenant-instrument.html;
// INV-02, INV-04, INV-05). A disclosure list: every version a unit has ever
// carried stays on its own chip, so choosing one never depends on today's
// date, and "Show what changed" opens the sentence-level diff between two of
// them. A unit with no version of its own still shows its children.
//
// A version's `text` is the one resolved for this reader, not the full set
// of translations (that is the obligation card's own shape): there is no
// language here to name as "the original", so a machine translation is
// labelled on its own terms rather than through LegalText's `translatedFrom`,
// which needs that language and would otherwise have to guess it.

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
  const [showDiff, setShowDiff] = useState(false);
  const version = node.versions.find((row) => row.versionNumber === selected);
  const diff = useProvisionDiff(node.id, version?.text?.language ?? locale, showDiff);

  return (
    <li>
      <details open data-provision={node.stableKey}>
        <summary className="cursor-pointer py-1.5 font-medium">
          <span className="mr-1.5 font-mono text-meta text-muted">{node.refLabel}</span>
          {node.heading}
        </summary>
        <div className="py-2">
          {node.versions.length === 0 ? null : (
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

              {showDiff && diff.isError ? <ErrorState title={t('inventory.obligation.diffErrorTitle')} onRetry={() => void diff.refetch()} /> : null}
              {showDiff && diff.data !== undefined ? (
                <LegalText lang={diff.data.language} reference={node.refLabel}>
                  <DiffText segments={diff.data.segments} />
                </LegalText>
              ) : version === undefined || version.text === null ? null : (
                <>
                  {version.text.isMachine ? (
                    <p className="mb-2 text-meta font-medium text-brass" data-machine-translation="">
                      {t('inventory.instrument.provisionMachineTranslation')}
                    </p>
                  ) : null}
                  <LegalText lang={version.text.language} reference={node.refLabel}>
                    {version.text.text}
                  </LegalText>
                  {version.transitionalNote === '' ? null : (
                    <p className="mt-2 text-meta text-muted" data-transitional-note="">
                      {version.transitionalNote}
                    </p>
                  )}
                </>
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

export function ProvisionTree({ instrumentId }: { instrumentId: string }) {
  const t = useT();
  const provisions = useInstrumentProvisions(instrumentId);
  const nodes = provisions.data ?? [];

  return (
    <Panel title={t('inventory.instrument.provisionsTitle')} data-provision-tree="">
      {provisions.isPending ? (
        <LoadingState rows={2} />
      ) : provisions.isError ? (
        <ErrorState title={t('inventory.instrument.provisionsErrorTitle')} onRetry={() => void provisions.refetch()} />
      ) : nodes.length === 0 ? (
        <EmptyState title={t('inventory.instrument.provisionsEmpty.title')} body={t('inventory.instrument.provisionsEmpty.body')} />
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
