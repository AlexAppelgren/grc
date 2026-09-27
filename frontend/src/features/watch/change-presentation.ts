import { byOrder, type KindRef, type PresentedPill, type VocabularyRef } from '@/features/shared/presentation-types';
import { slotTone, urgencyTone, type UrgencyKind } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { formatPartialDate, type DatePrecision, type FormatContext } from '@/shared/utils/format';

import type { AgentRef, ChangeRow, LibraryRef } from './api';

// Change row and header (design/system/pills-and-labels.md, slot order):
// change type, urgency, flags, the "Suggested by the agent" marker, library
// tags, tenant tags, then workflow status on the header only. Authority and
// date follow as plain meta text, which the screen renders itself.

export interface ChangeFacts {
  type: VocabularyRef;
  /** Absent when no urgency is known, or when its key is outside the severity scale below. */
  urgency?: KindRef<UrgencyKind>;
  flags: readonly VocabularyRef[];
  /** True while any classification on the record is still an agent's suggestion (WAT-03). */
  suggested?: boolean;
  /** True when an independent agent confirmed a classification and no person has (D-74); shown only when nothing is still suggested. */
  machineConfirmed?: boolean;
  libraryTags?: readonly VocabularyRef[];
  tenantTags?: readonly VocabularyRef[];
  workflowStatus?: VocabularyRef;
}

export type ChangeView = 'row' | 'header';

export const CHANGE_SLOT_ORDER = {
  type: 10,
  urgency: 20,
  flags: 30,
  suggested: 35,
  libraryTags: 40,
  tenantTags: 50,
  workflowStatus: 60,
} as const;

export function presentChange(change: ChangeFacts, view: ChangeView, t?: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `type:${change.type.key}`, label: change.type.label, tone: slotTone.changeType, order: CHANGE_SLOT_ORDER.type },
    ...(change.urgency === undefined
      ? []
      : [
          {
            key: `urgency:${change.urgency.key}`,
            label: change.urgency.label,
            tone: urgencyTone[change.urgency.kind],
            order: CHANGE_SLOT_ORDER.urgency,
          },
        ]),
    ...change.flags.map((flag, i) => ({
      key: `flag:${flag.key}`,
      label: flag.label,
      tone: slotTone.flag,
      order: CHANGE_SLOT_ORDER.flags + i,
    })),
    // A computed pill, so its words come from the catalog and not from the
    // API: the server sends `suggested` and `confirmedOrigin`, never a phrase.
    // A machine's confirmation keeps a label of its own, because only a
    // person's confirmation takes the AI label off (D-74).
    ...(change.suggested === true && t !== undefined
      ? [{ key: 'suggested', label: t('watch.row.suggestedByAgent'), tone: slotTone.suggested, order: CHANGE_SLOT_ORDER.suggested }]
      : change.machineConfirmed === true && t !== undefined
        ? [{ key: 'machine-confirmed', label: t('watch.row.machineConfirmed'), tone: slotTone.machineConfirmed, order: CHANGE_SLOT_ORDER.suggested }]
        : []),
    ...(change.libraryTags ?? []).map((tag, i) => ({
      key: `library-tag:${tag.key}`,
      label: tag.label,
      tone: slotTone.libraryTag,
      order: CHANGE_SLOT_ORDER.libraryTags + i,
    })),
    ...(change.tenantTags ?? []).map((tag, i) => ({
      key: `tenant-tag:${tag.key}`,
      label: tag.label,
      tone: slotTone.tenantTag,
      order: CHANGE_SLOT_ORDER.tenantTags + i,
      outlined: true,
    })),
  ];
  if (view === 'header' && change.workflowStatus !== undefined) {
    pills.push({
      key: `status:${change.workflowStatus.key}`,
      label: change.workflowStatus.label,
      tone: slotTone.workflowStatus,
      order: CHANGE_SLOT_ORDER.workflowStatus,
    });
  }
  return pills.sort(byOrder);
}

// ---------------------------------------------------------------------------
// From what the API sends to what the contract above reads
// ---------------------------------------------------------------------------

/**
 * The urgency keys the severity scale orders, in that order (WAT-03,
 * NFR-03). The tone comes from the key and from nothing else: the row's own
 * `kind` is deliberately null on the wire, because an urgency row's stored
 * kind is its tone and a tone is nobody's to send. A key outside this scale
 * — one an admin added — gets no pill rather than a guessed tone, exactly as
 * an unknown compliance kind does in the library.
 */
const URGENCY_KEYS: readonly UrgencyKind[] = ['act_now', 'within_3_months', 'six_months_plus', 'monitor', 'no_action'];

export function urgencyOf(ref: LibraryRef | null | undefined): KindRef<UrgencyKind> | null {
  if (ref === null || ref === undefined) return null;
  if (!(URGENCY_KEYS as readonly string[]).includes(ref.key)) return null;
  return { key: ref.key, label: ref.label, kind: ref.key as UrgencyKind };
}

/**
 * The urgency a row shows: this bank's own where it has a case, the library's
 * suggestion otherwise. The same rule the feed's urgency filter applies, so a
 * filter and a row can never disagree.
 */
export function rowUrgency(row: ChangeRow): KindRef<UrgencyKind> | null {
  return urgencyOf(row.case === null ? row.suggestedUrgency : (row.case.urgency ?? row.suggestedUrgency));
}

/** True while any classification on the record is still an agent's suggestion (WAT-03, AGT-02). */
export function isSuggested(row: ChangeRow): boolean {
  return row.changeType.suggested || row.flags.some((flag) => flag.suggested) || row.terms.some((term) => term.suggested);
}

/** True when an independent agent confirmed any classification on the record (D-74). */
export function isMachineConfirmed(row: ChangeRow): boolean {
  return [row.changeType, ...row.flags, ...row.terms].some((fact) => fact.confirmedOrigin === 'agent');
}

/** Who suggested a curated fact and who confirmed it, as every read of one answers it (D-74). */
export interface FactProvenance {
  confirmedOrigin?: 'agent' | 'user' | null;
  suggestedByAgent?: AgentRef | null;
  confirmedByAgent?: AgentRef | null;
}

/**
 * "Machine-confirmed: suggested by watch-sweeper, confirmed by
 * library-confirmer" for the facts an independent agent confirmed, each pair
 * of agents once; null when none did. A person's confirmation is never read
 * here, so a machine's can never borrow its words (D-74). The agents are
 * named by their definition keys, which never change.
 */
export function machineConfirmedBy(facts: readonly FactProvenance[], t: Translate): string | null {
  const sentences = new Set<string>();
  for (const fact of facts) {
    if (fact.confirmedOrigin !== 'agent' || !fact.confirmedByAgent) continue;
    const confirmer = fact.confirmedByAgent.key;
    sentences.add(
      fact.suggestedByAgent
        ? t('watch.fact.machineConfirmed', { suggester: fact.suggestedByAgent.key, confirmer })
        : t('watch.fact.machineConfirmedBy', { confirmer }),
    );
  }
  return sentences.size === 0 ? null : [...sentences].join(' · ');
}

export type CaseCategory = NonNullable<ChangeRow['case']>['category'];

/**
 * The seven fixed case categories and the phrase each one reads as. They are
 * kinds in code, not vocabulary rows, so their words live in the catalog:
 * `new` reads "Needs triage", never "new".
 */
const CASE_STATUS_KEY = {
  new: 'watch.case.status.new',
  assigned: 'watch.case.status.assigned',
  assessing: 'watch.case.status.assessing',
  implementing: 'watch.case.status.implementing',
  signoff: 'watch.case.status.signoff',
  closed: 'watch.case.status.closed',
  dismissed: 'watch.case.status.dismissed',
} as const satisfies Record<CaseCategory, MessageKey>;

export function caseStatusLabel(category: CaseCategory, t: Translate): string {
  return t(CASE_STATUS_KEY[category]);
}

/** What a case's status reads from: its fixed category and the bank's own sub-status inside it, if any. */
export interface CaseStatusFacts {
  category: CaseCategory;
  subStatus?: { key: string; label: string } | null;
}

/**
 * The workflow status a header or a row shows: the bank's own sub-status label
 * where the case carries one ("Waiting for legal" under assessing), the
 * category's phrase otherwise. The key stays the category's, because a
 * sub-status changes the words and never the tone or what a guard reads (CAS-S13).
 */
export function workflowStatusOf(caseFacts: CaseStatusFacts, t: Translate): VocabularyRef {
  const label = caseFacts.subStatus?.label ?? caseStatusLabel(caseFacts.category, t);
  return { key: caseFacts.category, label };
}

export function factsOfChange(row: ChangeRow, t: Translate): ChangeFacts {
  const urgency = rowUrgency(row);
  return {
    type: { key: row.changeType.ref.key, label: row.changeType.ref.label },
    ...(urgency === null ? {} : { urgency }),
    flags: row.flags.map((flag) => ({ key: flag.ref.key, label: flag.ref.label })),
    suggested: isSuggested(row),
    machineConfirmed: isMachineConfirmed(row),
    ...(row.case === null ? {} : { workflowStatus: workflowStatusOf(row.case, t) }),
  };
}

/** The row's pills, in slot order, from the row the API sent. */
export function presentChangeRow(row: ChangeRow, view: ChangeView, t: Translate): PresentedPill[] {
  return presentChange(factsOfChange(row, t), view, t);
}

// ---------------------------------------------------------------------------
// The plain meta text beside the pills
// ---------------------------------------------------------------------------

/** "Finansinspektionen, 15 Sep 2026", or the authority alone when the source states no date. */
export function authorityAndDate(row: ChangeRow, t: Translate, ctx: FormatContext): string {
  if (row.publishedOn === null) return row.authorityLabel;
  return t('watch.row.authorityAndDate', {
    authority: row.authorityLabel,
    date: formatPartialDate(row.publishedOn, row.publishedPrecision ?? 'day', ctx),
  });
}

/**
 * "In force 1 Oct 2026" plus "in 12 days" while the date is ahead, or the
 * source's own words for a date it has not set. `today` is passed in rather
 * than read from the clock, so a fixture cannot drift as the day moves.
 */
export function keyDateMeta(row: ChangeRow, t: Translate, ctx: FormatContext, today: Date): string[] {
  const label = row.keyDateLabel ?? '';
  if (row.keyDate === null) {
    return [label === '' ? t('watch.row.dateNotSet') : t('watch.row.keyDate', { label, date: t('watch.row.dateNotSet') })];
  }
  const date = formatPartialDate(row.keyDate, (row.keyDatePrecision ?? 'day') as DatePrecision, ctx);
  const meta = [label === '' ? date : t('watch.row.keyDate', { label, date })];
  const days = daysUntil(row.keyDate, today);
  if (days !== null && days > 0) meta.push(t('watch.row.daysLeft', { count: days }));
  return meta;
}

/** Whole days from `today` to a plain calendar date, or null when the string is not one. */
export function daysUntil(date: string, today: Date): number | null {
  const parsed = Date.parse(`${date.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(parsed)) return null;
  const from = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.round((parsed - from) / 86_400_000);
}

/** The scope terms a row carries, as the card's foot writes them; an empty list means no restriction. */
export function scopeTermLabels(row: ChangeRow): string[] {
  return row.terms.map((term) => term.ref.label);
}
