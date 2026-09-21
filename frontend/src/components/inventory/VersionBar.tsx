'use client';

import { Chip, ChipRow } from '@/components/ui/Chip';
import { TextInput } from '@/components/ui/Field';
import { useFormatContext } from '@/features/identity/hooks';
import type { ObligationVersionRow } from '@/features/library/types';
import { versionLabel } from '@/features/library/version-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';

// The version bar of the obligation card (design/screens/tenant-obligation.html;
// INV-04, AC-INV1): which versions exist, which one is on screen, the date the
// record is read as of, and "Show what changed". Choosing a version is choosing
// a date: the read always answers the version in force on the date asked for,
// so there is one source of truth and never two.

/**
 * The date that puts a version on screen: the day it took effect, or the last
 * day it was in force when it has been in force since the record began. A
 * version with neither is the only one there is, so today shows it and the
 * date is cleared.
 */
export function asOfFor(version: ObligationVersionRow): string {
  return version.effectiveFrom?.date ?? version.effectiveTo?.date ?? '';
}

export function VersionBar({
  versions,
  currentVersion,
  asOf,
  onAsOf,
  showDiff,
  onShowDiff,
}: {
  versions: readonly ObligationVersionRow[];
  /** The version in force on the read's date, or null when none is. */
  currentVersion: number | null;
  /** A plain date, YYYY-MM-DD; empty means today where the bank is. */
  asOf: string;
  onAsOf: (date: string) => void;
  showDiff: boolean;
  onShowDiff: (show: boolean) => void;
}) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    // ChipRow takes no pass-through attributes, so the journey's hook sits on
    // the element around it.
    <div data-version-bar="">
      <ChipRow className="mb-3">
        {versions.map((version) => (
          <Chip key={version.versionNumber} pressed={version.versionNumber === currentVersion} onClick={() => onAsOf(asOfFor(version))}>
            {versionLabel(version.versionNumber, version.effectiveFrom, t, ctx)}
          </Chip>
        ))}
        {versions.length > 1 ? (
          <Chip pressed={showDiff} onClick={() => onShowDiff(!showDiff)}>
            {t('inventory.obligation.showWhatChanged')}
          </Chip>
        ) : null}
        <label htmlFor="obligation-as-of" className="text-meta text-muted">
          {t('inventory.asOf')}
        </label>
        <TextInput id="obligation-as-of" type="date" className="w-auto" value={asOf} onChange={(event) => onAsOf(event.target.value)} />
      </ChipRow>
    </div>
  );
}
