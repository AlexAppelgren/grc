'use client';

import Link from 'next/link';

import { PillRow } from '@/components/ui/PillRow';
import { useFormatContext } from '@/features/identity/hooks';
import { machineConfirmedLabel, outsideFootprintLabel, presentObligation, type ObligationFacts } from '@/features/library/obligation-presentation';
import type { Obligation } from '@/features/library/types';
import { verifiedLabel, versionLabel } from '@/features/library/version-presentation';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';
import type { FormatContext } from '@/shared/utils/format';

// One row of the inventory (design/screens/tenant-inventory.html, the chunk 3
// row). The API sends facts; the pills come from presentObligation and the
// meta line from the version and verification labels. A row the footprint
// would hide is dashed and says which terms put it outside, and it is only
// ever asked for with "Show outside our scope" on.

/** The facts the pill contract reads, from the row the API sent. */
export function factsOf(obligation: Obligation): ObligationFacts {
  return {
    instrument: { key: obligation.instrument.key, label: obligation.instrument.shortName },
    binding: obligation.binding,
    complianceStatus: obligation.complianceStatus ?? undefined,
    changeWaitingForApproval: obligation.pendingApplicability === true,
    openChangeCount: obligation.openChangeCount,
    libraryTags: obligation.tags,
  };
}

/**
 * The meta line under the title: the terms the obligation carries in each
 * dimension it restricts, the version coming next, when it was last verified
 * and, outside the footprint, what puts it there. Wording in force that an
 * independent agent confirmed reads machine-confirmed in the verified date's
 * place until a named person re-verifies the record after it (INV-05, D-74).
 */
export function metaOf(obligation: Obligation, t: Translate, ctx: FormatContext): string[] {
  const meta = obligation.scope.filter((dimension) => dimension.terms.length > 0).map((dimension) => dimension.terms.map((term) => term.label).join(', '));
  if (obligation.upcomingVersion !== null) {
    meta.push(versionLabel(obligation.upcomingVersion.versionNumber, obligation.upcomingVersion.effectiveFrom, t, ctx));
  }
  const machine = machineConfirmedLabel(obligation.version, obligation, t, ctx);
  if (machine !== null) meta.push(machine);
  else if (obligation.lastVerifiedAt !== null) meta.push(verifiedLabel(obligation.lastVerifiedAt, t, ctx));
  if (!obligation.inFootprint) {
    meta.push(outsideFootprintLabel(obligation.outsideReason.flatMap((reason) => reason.terms), t));
  }
  return meta;
}

export function ObligationRow({ obligation }: { obligation: Obligation }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Link
      href={`/inventory/obligations/${obligation.id}`}
      // A page of rows would otherwise prefetch a page of obligation cards
      // nobody asked for, which is a request per row against the reader's
      // own inventory.
      prefetch={false}
      data-obligation={obligation.stableKey}
      data-outside-footprint={obligation.inFootprint ? undefined : ''}
      className={cn('block rounded-card border bg-surface px-4 py-3.5 hover:border-fg', obligation.inFootprint ? 'border-line' : 'border-dashed border-line-control')}
    >
      <PillRow pills={presentObligation(factsOf(obligation), 'row', t)} />
      <h3 className="my-1.5 font-semibold">{obligation.title === null ? obligation.refLabel : obligation.title.text}</h3>
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-muted">
        <span className="font-mono">{obligation.refLabel}</span>
        {metaOf(obligation, t, ctx).map((line, index) => (
          // Two dimensions can hold the same terms, so the position is the key.
          <span key={index}>{line}</span>
        ))}
      </p>
    </Link>
  );
}
