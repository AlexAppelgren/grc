import type { PartialDate } from '@/features/shared/presentation-types';
import { localeTags, type Locale, type Translate } from '@/shared/i18n';
import { formatDate, formatPartialDate, type FormatContext } from '@/shared/utils/format';

// Version, in-force and verification labels for the inventory, the
// obligation card and the provision tree (design/screens/tenant-obligation.html,
// tenant-instrument.html). Legal dates render with their precision
// (formatPartialDate); a missing effective date means "since always" (INV-04).

function partial(value: PartialDate, ctx: FormatContext): string {
  return formatPartialDate(value.date, value.precision, ctx);
}

/** "Version 1", or "Version 2, from 1 Oct 2026" when the version has an effective date. */
export function versionLabel(versionNumber: number, effectiveFrom: PartialDate | null, t: Translate, ctx: FormatContext): string {
  if (effectiveFrom === null) return t('version.label', { number: versionNumber });
  return t('version.labelFrom', { number: versionNumber, date: partial(effectiveFrom, ctx) });
}

/** "In force 3 Jan 2018 to 30 Sept 2026", "In force from 1 Oct 2026", "In force until …" or "In force". */
export function inForceLabel(from: PartialDate | null, to: PartialDate | null, t: Translate, ctx: FormatContext): string {
  if (from !== null && to !== null) return t('version.inForceRange', { from: partial(from, ctx), to: partial(to, ctx) });
  if (from !== null) return t('version.inForceFrom', { from: partial(from, ctx) });
  if (to !== null) return t('version.inForceUntil', { to: partial(to, ctx) });
  return t('version.inForce');
}

/** "Verified 30 Jun 2026": the day of the last verification in the tenant timezone (INV-06). */
export function verifiedLabel(lastVerifiedAt: string, t: Translate, ctx: FormatContext): string {
  return t('library.verified', { date: formatDate(lastVerifiedAt, ctx) });
}

/** A content language's name in the user language: "Swedish", "svenska"; a code it has no name for reads as the code. */
export function languageName(code: string, locale: Locale): string {
  return new Intl.DisplayNames([localeTags[locale]], { type: 'language', fallback: 'none' }).of(code) ?? code;
}
