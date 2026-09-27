import { pillTones, type PillTone } from '@/components/ui/pill-tones';
import type { Home } from '@/features/home/types';
import { complianceTone, type ComplianceKind } from '@/features/shared/tone-by-kind';
import type { VocabularyRow } from '@/features/vocabularies/types';
import type { MessageKey } from '@/shared/i18n/messages';

// "Where we stand" on Today (design/screens/tenant-today.html; HOM-01): the
// obligations that apply, one line per fixed compliance category in its own
// tone, and the open gaps. `GET /home` counts per category; the inventory
// filters by a status key, so each category links through the bank's own
// status of that category: its system row, or the first it added, while a
// retired row never filters. A category with no status to filter by, or the
// list still loading, is plain text rather than a link to the wrong list.

export type Standing = NonNullable<Home['standing']>;

export interface StandingLine {
  key: ComplianceKind;
  message: MessageKey;
  count: number;
  tone: PillTone;
  /** The tone's strong colour, for the bar's segment: a CSS value. */
  color: string;
  href: string | null;
}

export interface PresentedStanding {
  applyingHref: string;
  gapsHref: string;
  lines: StandingLine[];
  /** Nothing applies and no gap is open: the panel's empty state. */
  empty: boolean;
}

const CATEGORIES: readonly { key: ComplianceKind; field: 'compliant' | 'partly' | 'gap' | 'notAssessed'; message: MessageKey }[] = [
  { key: 'compliant', field: 'compliant', message: 'today.standing.compliant' },
  { key: 'partly', field: 'partly', message: 'today.standing.partly' },
  { key: 'gap', field: 'gap', message: 'today.standing.gap' },
  { key: 'not_assessed', field: 'notAssessed', message: 'today.standing.notAssessed' },
];

const APPLYING = '/inventory?applicability=applies';

function statusKeyOf(kind: ComplianceKind, statuses: readonly VocabularyRow[]): string | null {
  const live = statuses.filter((row) => row.active && row.kind === kind);
  return (live.find((row) => row.isSystem) ?? live[0])?.key ?? null;
}

export function presentStanding(standing: Standing, statuses: readonly VocabularyRow[] | undefined): PresentedStanding {
  const lines = CATEGORIES.map(({ key, field, message }) => {
    const status = statuses === undefined ? null : statusKeyOf(key, statuses);
    const tone = complianceTone[key];
    return {
      key,
      message,
      count: standing[field],
      tone,
      color: `var(${pillTones[tone].text})`,
      href: status === null ? null : `${APPLYING}&complianceStatus=${encodeURIComponent(status)}`,
    };
  });
  return { applyingHref: APPLYING, gapsHref: '/gaps', lines, empty: standing.applying === 0 && standing.openGaps === 0 };
}
