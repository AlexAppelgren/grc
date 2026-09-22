'use client';

import Link from 'next/link';

import { PillRow } from '@/components/ui/PillRow';
import { useFormatContext } from '@/features/identity/hooks';
import { presentInstrument, type InstrumentFacts } from '@/features/library/instrument-presentation';
import type { Instrument } from '@/features/library/types';
import { inForceLabel } from '@/features/library/version-presentation';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';
import type { FormatContext } from '@/shared/utils/format';

// One row of the Instruments tab (design/screens/tenant-inventory.html; INV-01,
// FP-03). The API sends facts; the pills come from presentInstrument, shared
// with the instrument card's header. A row the footprint would hide is dashed,
// exactly like an obligation row, and only ever shown with "Show outside footprint".

/** The facts the pill contract reads, from the row the API sent. */
export function factsOf(instrument: Instrument): InstrumentFacts {
  return {
    instrument: { key: instrument.stableKey, label: instrument.shortName },
    level: { key: instrument.level.key, label: instrument.level.label },
    binding: instrument.binding,
    jurisdiction: { key: instrument.jurisdiction.key, label: instrument.jurisdiction.label },
    ...(instrument.regime === null ? {} : { regime: { key: instrument.regime.key, label: instrument.regime.label } }),
  };
}

/** The meta line: who issued it, when it took effect, what it implements and how many obligations it carries. */
export function metaOf(instrument: Instrument, t: Translate, ctx: FormatContext): string[] {
  const meta: string[] = [];
  if (instrument.authority !== null) meta.push(instrument.authority.name);
  meta.push(inForceLabel(instrument.inForceFrom, instrument.inForceTo, t, ctx));
  if (instrument.implementsNote !== '') meta.push(t('inventory.instrument.implementsMeta', { note: instrument.implementsNote }));
  meta.push(t('inventory.count', { count: instrument.obligationCount }));
  return meta;
}

export function InstrumentRow({ instrument }: { instrument: Instrument }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Link
      href={`/inventory/instruments/${instrument.id}`}
      prefetch={false}
      data-instrument={instrument.stableKey}
      data-outside-footprint={instrument.inFootprint ? undefined : ''}
      className={cn('block rounded-card border bg-surface px-4 py-3.5 hover:border-fg', instrument.inFootprint ? 'border-line' : 'border-dashed border-line-control')}
    >
      <PillRow pills={presentInstrument(factsOf(instrument), t)} />
      <h3 className="my-1.5 font-semibold">{instrument.name === null ? instrument.shortName : instrument.name.text}</h3>
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-muted">
        {metaOf(instrument, t, ctx).map((line, index) => (
          // Two facts can read the same, so the position is the key.
          <span key={index}>{line}</span>
        ))}
      </p>
    </Link>
  );
}
