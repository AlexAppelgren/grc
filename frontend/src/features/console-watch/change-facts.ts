'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';
import { api } from '@/shared/utils/api-client';
import { formatDateTime, formatPartialDate, type DatePrecision, type FormatContext } from '@/shared/utils/format';
import type { components, operations } from '@/types/api.generated';

// The console's Change facts queue (WAT-03, WAT-04, ADM-02): its reads, its
// query keys and the pills of one row. It is bleqq's own view of the shared
// library, so nothing here joins a bank: `GET /console/changes` answers the
// library record and the facts an agent put forward, and no case, owner,
// footprint verdict or problem report exists on this shape to render.
//
// It is the screen's only read. The card's authority filter would need
// `GET /authorities`, which is gated on `library.read` inside a tenant and so
// answers 403 to a console session; the filter waits for that gate to admit a
// library editor, as the source reads already do (reported).

type Schemas = components['schemas'];

/** One queue row: the library change and the facts an agent proposed for it. */
export type ConsoleChangeRow = Schemas['WatchConsoleChangeRow'];
export type ConsoleChangePage = Schemas['WatchConsoleChangePage'];
/** `{ref: {key, kind, label}, confidence, suggested}` — the vocabulary row is under `ref`. */
export type ChangeFact = Schemas['WatchFact'];
export type ObligationLink = Schemas['WatchObligationLink'];

/** The queue's filters, exactly as the route declares them. */
export type ConsoleChangeQuery = NonNullable<operations['listConsoleChanges']['parameters']['query']>;

const CONSOLE_CHANGES = '/api/v1/console/changes';

/** The page the queue asks for; the route caps a page at 100. */
export const CONSOLE_CHANGES_PAGE = 20;

export async function listConsoleChanges(query: ConsoleChangeQuery = {}): Promise<ConsoleChangePage> {
  return (await api.get<ConsoleChangePage>(CONSOLE_CHANGES, { params: query })).data;
}

export const consoleChangeKeys = {
  changes: (query: ConsoleChangeQuery) => ['console', 'changes', query] as const,
};

export function useConsoleChanges(query: ConsoleChangeQuery): UseQueryResult<ConsoleChangePage> {
  return useQuery({ queryKey: consoleChangeKeys.changes(query), queryFn: () => listConsoleChanges(query) });
}

// ---------------------------------------------------------------------------
// Presentation
// ---------------------------------------------------------------------------

// Slot order from design/system/pills-and-labels.md, as the change facts card
// draws it: change type, flags, scope, the suggestion marker, then how much of
// the row is still nobody's word but an agent's. Urgency has no slot here: it
// is the library's starting point for a bank's triage and the queue row does
// not carry it.
export const CONSOLE_CHANGE_SLOT_ORDER = {
  type: 10,
  flags: 30,
  terms: 40,
  suggested: 50,
  unconfirmed: 60,
} as const;

/** True while any fact on the row is still an agent's suggestion nobody has confirmed. */
export function hasSuggestedFact(row: ConsoleChangeRow): boolean {
  return row.changeType.suggested || row.flags.some((f) => f.suggested) || row.terms.some((f) => f.suggested);
}

export function presentConsoleChange(row: ConsoleChangeRow, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `type:${row.changeType.ref.key}`, label: row.changeType.ref.label, tone: slotTone.changeType, order: CONSOLE_CHANGE_SLOT_ORDER.type },
    ...row.flags.map((flag, i) => ({ key: `flag:${flag.ref.key}`, label: flag.ref.label, tone: slotTone.flag, order: CONSOLE_CHANGE_SLOT_ORDER.flags + i })),
    ...row.terms.map((term, i) => ({ key: `term:${term.ref.key}`, label: term.ref.label, tone: slotTone.scopeTerm, order: CONSOLE_CHANGE_SLOT_ORDER.terms + i })),
  ];
  // Computed pills: the words come from the catalog, because the server sends
  // `suggested` and a count and never a phrase.
  if (hasSuggestedFact(row)) {
    pills.push({ key: 'suggested', label: t('console.changeFacts.suggestedMarker'), tone: slotTone.suggested, order: CONSOLE_CHANGE_SLOT_ORDER.suggested });
  }
  pills.push(
    row.unconfirmedCount > 0
      ? { key: 'unconfirmed', label: t('console.changeFacts.factsToConfirm', { count: row.unconfirmedCount }), tone: slotTone.factsToConfirm, order: CONSOLE_CHANGE_SLOT_ORDER.unconfirmed }
      : { key: 'confirmed', label: t('console.changeFacts.confirmed'), tone: slotTone.confirmed, order: CONSOLE_CHANGE_SLOT_ORDER.unconfirmed },
  );
  return pills.sort(byOrder);
}

/** "Finansinspektionen · Published 15 Sep 2026", or the authority alone when the source states no date. */
export function authorityAndPublished(row: ConsoleChangeRow, t: Translate, ctx: FormatContext): string {
  if (row.publishedOn === null) return row.authorityLabel;
  return t('console.changeFacts.publishedBy', {
    authority: row.authorityLabel,
    date: formatPartialDate(row.publishedOn, (row.publishedPrecision ?? 'day') as DatePrecision, ctx),
  });
}

/** When bleqq first saw the reform. The queue is ordered by it, so every row says it. */
export function firstSeen(row: ConsoleChangeRow, t: Translate, ctx: FormatContext): string {
  return t('console.changeFacts.firstSeen', { date: formatDateTime(row.firstSeenAt, ctx) });
}

/**
 * "Suggested by the agent, confidence 0.86", or the marker alone when nobody
 * recorded a confidence. The number is the model's own and orders a list; it
 * says nothing about whether the fact is right, which is why a confirmed fact
 * reads as confirmed instead.
 */
export function factProvenance(fact: { confidence: number | null; suggested: boolean }, t: Translate): string {
  if (!fact.suggested) return t('console.changeFacts.factConfirmed');
  if (fact.confidence === null) return t('console.changeFacts.suggestedMarker');
  return t('console.changeFacts.suggestedWithConfidence', { confidence: fact.confidence.toFixed(2) });
}

/** The same sentence for an obligation link, whose confirmation is a flag rather than a marker. */
export function linkProvenance(link: ObligationLink, t: Translate): string {
  return factProvenance({ confidence: link.confidence, suggested: !link.confirmed }, t);
}
