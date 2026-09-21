import type { PillTone } from '@/components/ui/pill-tones';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { proposalStatusTone, slotTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { ObligationVersionPayload, ProposalKind, ProposalRow, ProposalStatus, VocabularyProposalPayload } from './types';

// Pills and derived facts for the console queue (design/screens/console-queue.html;
// PRO-01, PRO-02, PRO-03, AC-PRO2). Tone is never chosen by a person: the kind pill
// sits in the same slot a change type does (notice), the status pill's tone comes
// from the fixed status kind, and "Yours" is the computed `you` slot (positive).
//
// GET /proposals and GET /proposals/{id} answer the plain `ProposalRow` on `main`
// today (chunk4-T10's enrichment — target title, target reference, instrument short
// name, a server-computed `isMine`, `fromOrganisation` — is not built yet). `isMine`
// is therefore computed here from `proposedBy.id`, which the row already carries for
// a proposal this reader may see decided; that is not a new disclosure; a proposal
// made in a bank never reaches the console with a proposer at all).

const SLOT_ORDER = { kind: 10, status: 20, yours: 30 } as const;

const KIND_LABEL: Readonly<Record<ProposalKind, MessageKey>> = {
  new_obligation_version: 'console.queue.kind.newObligationVersion',
  vocabulary_create: 'console.queue.kind.vocabulary',
  vocabulary_relabel: 'console.queue.kind.vocabulary',
  vocabulary_retire: 'console.queue.kind.vocabulary',
  vocabulary_restore: 'console.queue.kind.vocabulary',
  vocabulary_merge: 'console.queue.kind.vocabulary',
  term_create: 'console.queue.kind.vocabulary',
  term_update: 'console.queue.kind.vocabulary',
};

const STATUS_LABEL: Readonly<Record<ProposalStatus, MessageKey>> = {
  open: 'console.queue.status.open',
  approved: 'console.queue.status.approved',
  rejected: 'console.queue.status.rejected',
  superseded: 'console.queue.status.superseded',
};

function isProposalKind(value: string): value is ProposalKind {
  return value in KIND_LABEL;
}

function isProposalStatus(value: string): value is ProposalStatus {
  return value in STATUS_LABEL;
}

export function kindLabel(kind: string, t: Translate): string {
  return t(isProposalKind(kind) ? KIND_LABEL[kind] : 'console.queue.kind.other');
}

export function statusLabel(status: string, t: Translate): string {
  return t(isProposalStatus(status) ? STATUS_LABEL[status] : 'console.queue.status.other');
}

export function statusTone(status: string): PillTone {
  return isProposalStatus(status) ? proposalStatusTone[status] : 'information';
}

/** The signed-in reader made this proposal: computed client-side from the row's own `proposedBy.id` (see the module note). */
export function isMineOf(row: Pick<ProposalRow, 'proposedBy'>, meId: string | null): boolean {
  return meId !== null && row.proposedBy?.id === meId;
}

export function presentProposal(row: Pick<ProposalRow, 'kind' | 'status'>, isMine: boolean, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: 'kind', label: kindLabel(row.kind, t), tone: slotTone.proposalKind, order: SLOT_ORDER.kind },
    { key: 'status', label: statusLabel(row.status, t), tone: statusTone(row.status), order: SLOT_ORDER.status },
  ];
  if (isMine) pills.push({ key: 'yours', label: t('console.queue.yours'), tone: slotTone.you, order: SLOT_ORDER.yours });
  return pills.sort(byOrder);
}

/**
 * Who proposed it, in one line. `proposedBy` is null for an agent's proposal and for one
 * made inside a bank alike (a bank member's identity never reaches the console); the two
 * are told apart here by `agentRunId`, since `fromOrganisation` is not on the wire yet
 * (see the module note) — a tenant-made proposal without an agent run therefore also
 * falls back to the organisation phrase, which is the same words the enrichment would
 * have shown it under.
 */
export function proposerLine(row: Pick<ProposalRow, 'proposedBy' | 'agentRunId' | 'model'>, t: Translate): string {
  if (row.proposedBy !== null && row.proposedBy !== undefined) return row.proposedBy.name;
  if (row.agentRunId !== null && row.agentRunId !== undefined) return row.model.trim() || t('console.queue.proposedByAgent');
  return t('console.queue.proposedByOrganisation');
}

export function sourceLine(row: Pick<ProposalRow, 'sourceLabel'>, t: Translate): string | null {
  return row.sourceLabel.trim() === '' ? null : t('console.queue.source', { source: row.sourceLabel });
}

// ——— payload readers ——————————————————————————————————————————————

export function isObligationVersion(kind: string): boolean {
  return kind === 'new_obligation_version';
}

export function isVocabularyKind(kind: string): boolean {
  return kind !== 'new_obligation_version';
}

export function obligationPayloadOf(row: Pick<ProposalRow, 'payload'>): ObligationVersionPayload | null {
  const payload = (row.payload ?? {}) as Record<string, unknown>;
  if (typeof payload.summaries !== 'object' || payload.summaries === null) return null;
  return payload as unknown as ObligationVersionPayload;
}

export function vocabularyPayloadOf(row: Pick<ProposalRow, 'payload'>): VocabularyProposalPayload {
  return (row.payload ?? {}) as unknown as VocabularyProposalPayload;
}

/** The per-field source panel beside "What changes": one line per field the proposal sources, in a fixed, readable order. */
export function fieldSourceLabel(field: string, languageName: (code: string) => string, t: Translate): string {
  if (field === 'effectiveFrom') return t('console.queue.field.effectiveFrom');
  if (field === 'terms') return t('console.queue.field.scope');
  if (field.startsWith('summaries.')) return t('console.queue.field.text', { language: languageName(field.slice('summaries.'.length)) });
  return field;
}

const FIELD_ORDER = ['summaries', 'effectiveFrom', 'terms'] as const;

function fieldRank(field: string): number {
  const group = field.startsWith('summaries.') ? 'summaries' : field;
  const index = (FIELD_ORDER as readonly string[]).indexOf(group);
  return index === -1 ? FIELD_ORDER.length : index;
}

/** `fieldSources` as ordered `{field, url}` rows: summaries first (language order), then the effective date, then scope. */
export function fieldSourceRows(fieldSources: Record<string, string>): { field: string; url: string }[] {
  return Object.entries(fieldSources)
    .map(([field, url]) => ({ field, url }))
    .sort((a, b) => fieldRank(a.field) - fieldRank(b.field) || a.field.localeCompare(b.field));
}

/** The proposed scope as `brand` pills, in the scope block's own slot (pills-and-labels.md). */
export function scopeTermPills(refs: readonly string[], labelOf: (ref: string) => string): PresentedPill[] {
  return refs.map((ref, index) => ({ key: `term:${ref}`, label: labelOf(ref), tone: slotTone.scopeTerm, order: index }));
}
