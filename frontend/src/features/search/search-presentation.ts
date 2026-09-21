import { byOrder, type KindRef, type PresentedPill, type VocabularyRef } from '@/features/shared/presentation-types';
import { slotTone, urgencyTone, type UrgencyKind } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { formatDate, type FormatContext } from '@/shared/utils/format';

import type { SearchHit, SearchMatchKind } from './types';

// The result row (design/screens/tenant-search.html, pills-and-labels.md
// "Obligation row" slot order): instrument, then match kind, then
// "Guidance" when the record does not bind. Applicability and compliance
// status are the register overlay's (chunk 8) and carry nothing here; a
// registered change's urgency is included so this presentation keeps
// working once `c7-index-changes` starts sending one, but every hit today
// carries none (`apps/search/hybrid.py::_hit`).

export interface SearchHitFacts {
  instrument: VocabularyRef | null;
  matchKind: SearchMatchKind;
  guidance: boolean;
  urgency?: KindRef<UrgencyKind>;
}

export const SEARCH_HIT_SLOT_ORDER = {
  instrument: 10,
  matchKind: 20,
  guidance: 30,
  urgency: 40,
} as const;

const MATCH_KIND_KEY: Record<SearchMatchKind, MessageKey> = {
  keyword: 'search.matchKind.keyword',
  concept: 'search.matchKind.concept',
  both: 'search.matchKind.both',
};

export function matchKindLabel(kind: SearchMatchKind, t: Translate): string {
  return t(MATCH_KIND_KEY[kind]);
}

export function presentSearchHit(hit: SearchHitFacts, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    ...(hit.instrument === null
      ? []
      : [{ key: `instrument:${hit.instrument.key}`, label: hit.instrument.label, tone: slotTone.instrument, order: SEARCH_HIT_SLOT_ORDER.instrument }]),
    {
      key: `matchKind:${hit.matchKind}`,
      label: matchKindLabel(hit.matchKind, t),
      tone: slotTone.matchKind,
      order: SEARCH_HIT_SLOT_ORDER.matchKind,
    },
    ...(hit.guidance ? [{ key: 'guidance', label: t('search.guidance'), tone: slotTone.guidance, order: SEARCH_HIT_SLOT_ORDER.guidance }] : []),
    ...(hit.urgency === undefined
      ? []
      : [{ key: `urgency:${hit.urgency.key}`, label: hit.urgency.label, tone: urgencyTone[hit.urgency.kind], order: SEARCH_HIT_SLOT_ORDER.urgency }]),
  ];
  return pills.sort(byOrder);
}

// ---------------------------------------------------------------------------
// From what the API sends to what the contract above reads
// ---------------------------------------------------------------------------

const URGENCY_KEYS: readonly UrgencyKind[] = ['act_now', 'within_3_months', 'six_months_plus', 'monitor', 'no_action'];

export function factsOfHit(hit: SearchHit): SearchHitFacts {
  const urgency = hit.urgency;
  const known = urgency !== null && urgency !== undefined && (URGENCY_KEYS as readonly string[]).includes(urgency.key);
  return {
    instrument: hit.instrumentShortName === null || hit.instrumentShortName === undefined ? null : { key: hit.instrumentShortName, label: hit.instrumentShortName },
    matchKind: hit.matchKind,
    guidance: hit.binding === false,
    ...(known && urgency !== null && urgency !== undefined ? { urgency: { key: urgency.key, label: urgency.label, kind: urgency.key as UrgencyKind } } : {}),
  };
}

/** The row's pills, in slot order, from the hit the API sent. */
export function presentSearchHitRow(hit: SearchHit, t: Translate): PresentedPill[] {
  return presentSearchHit(factsOfHit(hit), t);
}

// ---------------------------------------------------------------------------
// The plain meta text beside the pills: version and validity (SRC-02,
// "mechanics" — a chunk copies its validity, so this needs no join).
// ---------------------------------------------------------------------------

export function versionMeta(hit: SearchHit, t: Translate): string | null {
  return hit.versionNo === null || hit.versionNo === undefined ? null : t('search.hit.version', { number: hit.versionNo });
}

export function validityMeta(hit: SearchHit, t: Translate, ctx: FormatContext): string | null {
  const from = hit.validFrom ?? null;
  const to = hit.validTo ?? null;
  if (from === null && to === null) return null;
  if (from !== null && to !== null) return t('search.hit.validRange', { from: formatDate(from, ctx), to: formatDate(to, ctx) });
  if (from !== null) return t('search.hit.validFrom', { date: formatDate(from, ctx) });
  return t('search.hit.validUntil', { date: formatDate(to as string, ctx) });
}

// ---------------------------------------------------------------------------
// The snippet, with the query's own words marked (SRC-02: "highlighted terms
// in the hit's own language"). The snippet already sits in that language —
// this only has to find the query's words inside it, whatever language they
// are in, which needs no language tag of its own.
// ---------------------------------------------------------------------------

export interface HighlightSegment {
  text: string;
  matched: boolean;
}

const WORD = /[\p{L}\p{N}]+/gu;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** A term under two characters is too common a fragment to mark on its own. */
export function highlightSnippet(snippet: string, query: string): HighlightSegment[] {
  const terms = [...new Set(Array.from(query.matchAll(WORD), (match) => match[0]).filter((word) => word.length >= 2))];
  if (terms.length === 0) return [{ text: snippet, matched: false }];
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'giu');
  const lower = terms.map((term) => term.toLowerCase());
  return snippet
    .split(pattern)
    .filter((part) => part !== '')
    .map((text) => ({ text, matched: lower.includes(text.toLowerCase()) }));
}
