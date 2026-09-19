import type { PillTone } from '@/components/ui/pill-tones';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';
import { formatDate } from '@/shared/utils/format';

import type { FootprintChangeRequest, FootprintDimension, FootprintPreview, FootprintPreviewCount, FootprintRequestStatus, TaxonomyTerm, TermChange, TermRef } from './types';

// Pills and derived facts for the footprint screen
// (design/screens/admin-footprint.html; FP-01, FP-02, AC-FP1). A scope term
// is always a brand pill. "Every service" stands for a dimension with every
// term selected; an empty dimension is plain text, because empty means no
// restriction (pills-and-labels.md, "Scope block").

export const FOUR_EYES_CODE = 'four_eyes_violation';
export const REQUEST_PENDING_CODE = 'request_pending';

export interface PresentedScope {
  pills: PresentedPill[];
  /** Set when the dimension holds no term: the text to show instead of pills. */
  emptyText: string | null;
}

export function presentScope(dimension: Pick<TermRef, 'label'>, terms: readonly TermRef[], allSelected: boolean, t: Translate): PresentedScope {
  if (terms.length === 0) return { pills: [], emptyText: t('footprint.notRestricted') };
  if (allSelected) {
    return { pills: [{ key: 'scope:all', label: t('footprint.allSelected', { dimension: dimension.label.toLowerCase() }), tone: slotTone.scopeTerm, order: 0 }], emptyText: null };
  }
  return { pills: terms.map((term, i) => ({ key: `term:${term.key}`, label: term.label, tone: slotTone.scopeTerm, order: i })), emptyText: null };
}

export function presentFootprintDimension(dimension: FootprintDimension, t: Translate): PresentedScope {
  return presentScope(dimension.dimension, dimension.terms, dimension.allSelected, t);
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

function labels(terms: readonly Pick<TermRef, 'label'>[]): string {
  return terms.map((term) => term.label).join(', ');
}

/** "Switch off Advice", "Add Fund company", or both: the request's title, built from its terms. */
export function requestTitle(request: Pick<FootprintChangeRequest, 'adds' | 'removes'>, t: Translate): string {
  const adds = labels(request.adds);
  const removes = labels(request.removes);
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

/** "Hides 4 obligations and 2 open cases", for the banner; counts not yet known are left out. */
export function previewSummary(preview: FootprintPreview | null | undefined, t: Translate): string {
  const parts = previewLines(preview, t)
    .hides.filter((line) => line.available)
    .map((line) => line.text);
  if (parts.length === 0) return t('footprint.preview.nothingCounted');
  return t('footprint.preview.hides', { what: parts.join(t('footprint.preview.and')) });
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

/** The terms a pending request is about to switch off in a dimension, so the chip can show it struck through. */
export function pendingRemovals(request: Pick<FootprintChangeRequest, 'removes'> | null, dimension: string): ReadonlySet<string> {
  return new Set((request?.removes ?? []).filter((term) => term.dimension === dimension).map((term) => term.key));
}

export function pendingAdditions(request: Pick<FootprintChangeRequest, 'adds'> | null, dimension: string): ReadonlySet<string> {
  return new Set((request?.adds ?? []).filter((term) => term.dimension === dimension).map((term) => term.key));
}

/** The terms of a dimension not yet in the footprint, offered by the chip adder. */
export function termsOutside(all: readonly TaxonomyTerm[], dimension: FootprintDimension): TaxonomyTerm[] {
  const held = new Set(dimension.terms.map((term) => term.key));
  return all.filter((term) => term.dimension === dimension.dimension.key && term.active !== false && !held.has(term.key));
}

/** "Maria Ek approved "Switch off Tax" requested by Sara Lindqvist" plus the note, for the history. */
export function historyLine(request: FootprintChangeRequest, t: Translate, ctx: FormatContext): { when: string; who: string; text: string } {
  const title = requestTitle(request, t);
  const requester = request.requestedBy.name;
  const who = request.decidedBy?.name ?? requester;
  const when = formatDate(request.decidedAt ?? request.requestedAt, ctx);
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
