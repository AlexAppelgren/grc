import type { PillTone } from '@/components/ui/pill-tones';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';
import { formatDateTime } from '@/shared/utils/format';

import type { FootprintChangeRequest, FootprintDimension, FootprintPreview, FootprintPreviewCount, FootprintRequestStatus, TaxonomyTerm, TermChange, TermRef } from './types';

// Derived facts and pills for the regulatory scope screen
// (design/screens/admin-footprint.html; FP-01, FP-02, AC-FP1). The page reads
// the scope as groups of terms, held or not; an empty group means no
// restriction, and a term a waiting request changes carries a warning pill.

export const FOUR_EYES_CODE = 'four_eyes_violation';
export const REQUEST_PENDING_CODE = 'request_pending';

export interface ScopeGroupRow {
  term: TermRef;
  held: boolean;
}

export interface ScopeGroup {
  dimension: TermRef;
  rows: ScopeGroupRow[];
}

/** The groups the page shows (REGULATORY_SCOPE.md 4.2): a dimension appears when it
 * restricts the scope and has at least one active term, held or not. Channel, lifecycle
 * stage and theme never restrict, and a dimension without an active term has nothing to
 * offer, so both stay off the page. Each group lists every active term in the taxonomy's
 * order, held or not; one with nothing held is the unrestricted one. */
export function scopeGroups(dimensions: readonly FootprintDimension[], terms: readonly TaxonomyTerm[]): ScopeGroup[] {
  return dimensions
    .filter((d) => d.restrictsFootprint)
    .map((d) => {
      const held = new Set(d.terms.map((term) => term.key));
      return {
        dimension: d.dimension,
        rows: terms.filter((term) => term.dimension === d.dimension.key && term.active !== false).map((term) => ({ term, held: held.has(term.key) })),
      };
    })
    .filter((group) => group.rows.length > 0);
}

/** The groups a draft would start restricting (REGULATORY_SCOPE.md 4.3): empty in the
 * stored footprint, so today it narrows nothing, and non-empty in the draft — ticking the
 * first term in an empty group is the dangerous direction, because it can hide records for
 * every member that no preview line ever showed as "revealed". */
export function narrowedGroups(dimensions: readonly FootprintDimension[], draft: FootprintDraft): FootprintDimension[] {
  return dimensions.filter((d) => d.terms.length === 0 && (draft[d.dimension.key]?.size ?? 0) > 0);
}

export function pendingTermPill(kind: 'add' | 'remove', t: Translate): PresentedPill {
  return { key: `pending:${kind}`, label: kind === 'add' ? t('footprint.pending.add') : t('footprint.pending.remove'), tone: slotTone.waitingForApproval, order: 0 };
}

// Request status is a kind: pending needs attention, approved is good, the
// other two are facts.
export const requestStatusTone: Record<FootprintRequestStatus, PillTone> = {
  pending: slotTone.waitingForApproval,
  approved: 'positive',
  rejected: 'information',
  withdrawn: 'information',
};

export function presentRequestStatus(status: FootprintRequestStatus, t: Translate): PresentedPill {
  const label =
    status === 'pending' ? t('pill.waitingForApproval') : status === 'approved' ? t('footprint.status.approved') : status === 'rejected' ? t('footprint.status.rejected') : t('footprint.status.withdrawn');
  return { key: `status:${status}`, label, tone: requestStatusTone[status], order: 0 };
}

/** "Advice", "Advice and Custody", "Advice, Custody and Tax". */
function labels(terms: readonly Pick<TermRef, 'label'>[], t: Translate): string {
  const names = terms.map((term) => term.label);
  if (names.length < 2) return names.join('');
  return `${names.slice(0, -1).join(', ')}${t('footprint.preview.and')}${names[names.length - 1]}`;
}

/** "Remove Advice", "Add Fund company", or both: the request's title, built from its terms. */
export function requestTitle(request: Pick<FootprintChangeRequest, 'adds' | 'removes'>, t: Translate): string {
  const adds = labels(request.adds, t);
  const removes = labels(request.removes, t);
  if (adds.length > 0 && removes.length > 0) return t('footprint.request.addAndRemove', { adds, removes });
  if (adds.length > 0) return t('footprint.request.add', { adds });
  return t('footprint.request.remove', { removes });
}

export interface PreviewLine {
  key: string;
  text: string;
  available: boolean;
}

function kindLabel(kind: string, count: number, t: Translate): string {
  if (kind === 'obligations') return t('footprint.preview.obligations', { count });
  if (kind === 'cases') return t('footprint.preview.cases', { count });
  return `${count} ${kind.replace(/[._-]/g, ' ')}`;
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function previewSide(side: Record<string, FootprintPreviewCount> | undefined, prefix: string, t: Translate): PreviewLine[] {
  return Object.entries(side ?? {}).map(([kind, entry]) => ({
    key: `${prefix}:${kind}`,
    text: entry.available ? kindLabel(kind, entry.count, t) : t('footprint.preview.notCounted', { kind: capitalise(kindLabel(kind, 0, t).replace(/^0 /, '')) }),
    available: entry.available,
  }));
}

/** One line per record kind for each side of the preview; "not counted yet" where the count is not known. */
export function previewLines(preview: FootprintPreview | null | undefined, t: Translate): { hides: PreviewLine[]; reveals: PreviewLine[] } {
  return { hides: previewSide(preview?.hidden, 'hides', t), reveals: previewSide(preview?.revealed, 'reveals', t) };
}

function counted(lines: readonly PreviewLine[], t: Translate): string {
  return lines
    .filter((line) => line.available)
    .map((line) => line.text)
    .join(t('footprint.preview.and'));
}

/** "Hides 2 obligations and reveals 1 obligation.", for the banner and the approve dialog; counts not yet known are left out. */
export function previewSummary(preview: FootprintPreview | null | undefined, t: Translate): string {
  const { hides, reveals } = previewLines(preview, t);
  const hidden = counted(hides, t);
  if (hidden.length === 0) return t('footprint.preview.nothingCounted');
  return t('footprint.preview.summary', { hides: hidden, reveals: counted(reveals, t) });
}

/** True when a counted record kind would be hidden: the change takes something away from every member. */
export function hidesSomething(preview: FootprintPreview | null | undefined): boolean {
  return Object.values(preview?.hidden ?? {}).some((entry) => entry.available && entry.count > 0);
}

export function isRequester(request: Pick<FootprintChangeRequest, 'requestedBy'>, userId: string | null | undefined): boolean {
  return userId !== null && userId !== undefined && request.requestedBy.id === userId;
}

export const FOOTPRINT_REQUEST = 'footprint.request';
export const FOOTPRINT_APPROVE = 'footprint.approve';

export function canApprove(request: Pick<FootprintChangeRequest, 'requestedBy' | 'status'>, userId: string | null | undefined, permissions: readonly string[]): boolean {
  return request.status === 'pending' && permissions.includes(FOOTPRINT_APPROVE) && !isRequester(request, userId);
}

export function canWithdraw(request: Pick<FootprintChangeRequest, 'requestedBy' | 'status'>, userId: string | null | undefined): boolean {
  return request.status === 'pending' && isRequester(request, userId);
}

/** The draft is the set of term keys per dimension; the diff against the stored footprint is what a request carries. */
export type FootprintDraft = Record<string, ReadonlySet<string>>;

export function draftOf(dimensions: readonly FootprintDimension[]): FootprintDraft {
  return Object.fromEntries(dimensions.map((d) => [d.dimension.key, new Set(d.terms.map((term) => term.key))]));
}

/** The scope a request leaves once approved: what the approver weighs narrowing against. */
export function draftAfter(dimensions: readonly FootprintDimension[], request: Pick<FootprintChangeRequest, 'adds' | 'removes'>): FootprintDraft {
  const draft = Object.fromEntries(dimensions.map((d) => [d.dimension.key, new Set(d.terms.map((term) => term.key))]));
  for (const term of request.adds) draft[term.dimension]?.add(term.key);
  for (const term of request.removes) draft[term.dimension]?.delete(term.key);
  return draft;
}

export function toggleTerm(draft: FootprintDraft, dimension: string, key: string): FootprintDraft {
  const current = new Set(draft[dimension] ?? []);
  if (current.has(key)) current.delete(key);
  else current.add(key);
  return { ...draft, [dimension]: current };
}

export function diffFootprint(dimensions: readonly FootprintDimension[], draft: FootprintDraft): { adds: TermChange[]; removes: TermChange[] } {
  const adds: TermChange[] = [];
  const removes: TermChange[] = [];
  for (const d of dimensions) {
    const stored = new Set(d.terms.map((term) => term.key));
    const wanted = draft[d.dimension.key] ?? stored;
    for (const key of wanted) if (!stored.has(key)) adds.push({ dimension: d.dimension.key, key });
    for (const key of stored) if (!wanted.has(key)) removes.push({ dimension: d.dimension.key, key });
  }
  return { adds, removes };
}

/** The terms a pending request removes from a dimension, each marked "Removed when approved". */
export function pendingRemovals(request: Pick<FootprintChangeRequest, 'removes'> | null, dimension: string): ReadonlySet<string> {
  return new Set((request?.removes ?? []).filter((term) => term.dimension === dimension).map((term) => term.key));
}

/** The terms a pending request adds to a dimension, each marked "Added when approved". */
export function pendingAdditions(request: Pick<FootprintChangeRequest, 'adds'> | null, dimension: string): ReadonlySet<string> {
  return new Set((request?.adds ?? []).filter((term) => term.dimension === dimension).map((term) => term.key));
}

/** "Maria Ek approved "Remove Tax" requested by Sara Lindqvist" plus the note, for the history. */
export function historyLine(request: FootprintChangeRequest, t: Translate, ctx: FormatContext): { when: string; who: string; text: string } {
  const title = requestTitle(request, t);
  const requester = request.requestedBy.name;
  const who = request.decidedBy?.name ?? requester;
  const when = formatDateTime(request.decidedAt ?? request.requestedAt, ctx);
  const text =
    request.status === 'approved'
      ? t('footprint.history.approved', { title, requester })
      : request.status === 'rejected'
        ? t('footprint.history.rejected', { title, requester, note: request.decisionNote })
        : request.status === 'withdrawn'
          ? t('footprint.history.withdrawn', { title })
          : t('footprint.history.pending', { title });
  return { when, who, text };
}
