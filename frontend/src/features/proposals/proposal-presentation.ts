import type { PillTone } from '@/components/ui/pill-tones';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { proposalStatusTone, slotTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';

import { TERM_KINDS, VOCABULARY_KINDS, type ObligationVersionPayload, type ProposalKind, type ProposalQueueRow, type ProposalRow, type ProposalStatus, type VocabularyProposalPayload } from './types';

// Pills and derived facts for the console queue (design/screens/console-queue.html;
// PRO-01, PRO-02, PRO-03, AC-PRO2). Tone is never chosen by a person: the kind pill
// sits in the same slot a change type does (notice), the status pill's tone comes
// from the fixed status kind, and "Yours" is the server's `isMine` in the `you` slot
// (positive). An agent that decided or corrected a proposal is named as an agent,
// never in a person's slot, and its decision reads as machine-confirmed.

const SLOT_ORDER = { kind: 10, status: 20, yours: 30 } as const;

const KIND_LABEL: Readonly<Record<ProposalKind, MessageKey>> = {
  new_instrument: 'console.queue.kind.newInstrument',
  new_obligation: 'console.queue.kind.newObligation',
  new_obligation_version: 'console.queue.kind.newObligationVersion',
  new_provision: 'console.queue.kind.newProvision',
  new_provision_version: 'console.queue.kind.newProvisionVersion',
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

export function presentProposal(row: Pick<ProposalQueueRow, 'kind' | 'status' | 'isMine'>, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: 'kind', label: kindLabel(row.kind, t), tone: slotTone.proposalKind, order: SLOT_ORDER.kind },
    { key: 'status', label: statusLabel(row.status, t), tone: statusTone(row.status), order: SLOT_ORDER.status },
  ];
  if (row.isMine === true) pills.push({ key: 'yours', label: t('console.queue.yours'), tone: slotTone.you, order: SLOT_ORDER.yours });
  return pills.sort(byOrder);
}

/**
 * Who proposed it, in one line: the platform person by name; the organisation phrase for
 * a proposal made inside a bank (`fromOrganisation`), whose people and agents never reach
 * the console by name; otherwise an agent, by the model that drafted it.
 */
export function proposerLine(row: Pick<ProposalRow, 'proposedBy' | 'fromOrganisation' | 'model'>, t: Translate): string {
  if (row.proposedBy !== null && row.proposedBy !== undefined) return row.proposedBy.name;
  if (row.fromOrganisation === true) return t('console.queue.proposedByOrganisation');
  return row.model.trim() || t('console.queue.proposedByAgent');
}

/** The library record a row would change, by its own title and instrument; null for a vocabulary change. */
export function targetLine(row: Pick<ProposalQueueRow, 'target'>, t: Translate): string | null {
  const target = row.target ?? null;
  if (target === null) return null;
  const title = target.title !== '' ? target.title : target.referenceLabel;
  return target.instrumentShortName === '' ? title : t('console.queue.target', { title, instrument: target.instrumentShortName });
}

type Decision = Pick<ProposalRow, 'status' | 'reviewedBy' | 'reviewedByAgent' | 'correctedByAgent' | 'reviewedAt' | 'appliedAt' | 'reviewNote'>;

/**
 * The decision in one sentence, dated and naming who decided: an agent by its key, as
 * machine-confirmed on an approval; a person by name; and nobody, rather than an empty
 * name, should a decided row name neither. Null while nothing is decided or dated.
 */
export function decisionLine(row: Decision, formatDate: (iso: string) => string, t: Translate): string | null {
  const agent = row.reviewedByAgent?.key;
  const name = row.reviewedBy?.name ?? '';
  const reviewer = name === '' ? undefined : name;
  if (row.status === 'approved' && typeof row.appliedAt === 'string') {
    const date = formatDate(row.appliedAt);
    if (agent !== undefined) return t('console.queue.detail.appliedByAgent', { date, agent });
    if (reviewer !== undefined) return t('console.queue.detail.appliedBy', { date, reviewer });
    return t('console.queue.detail.applied', { date });
  }
  if (row.status === 'rejected' && typeof row.reviewedAt === 'string') {
    const date = formatDate(row.reviewedAt);
    if (agent !== undefined) return t('console.queue.detail.rejectedByAgent', { date, agent });
    if (reviewer !== undefined) return t('console.queue.detail.rejectedBy', { date, reviewer });
    return t('console.queue.detail.rejected', { date });
  }
  return null;
}

/** The decider's note, labelled as the agent's when an agent decided (AI output stays labelled). */
export function decisionNoteLine(row: Decision, t: Translate): string | null {
  if (row.reviewNote === '') return null;
  const agentDecided = row.reviewedByAgent !== null && row.reviewedByAgent !== undefined;
  return t(agentDecided ? 'console.queue.detail.agentNote' : 'console.queue.detail.reviewNote', { note: row.reviewNote });
}

/** The agent that corrected the payload on the way to approving it, named as an agent. */
export function agentCorrectionLine(row: Decision, t: Translate): string | null {
  const agent = row.correctedByAgent?.key;
  return agent === undefined ? null : t('console.queue.detail.correctedByAgent', { agent });
}

export function sourceLine(row: Pick<ProposalRow, 'sourceLabel'>, t: Translate): string | null {
  return row.sourceLabel.trim() === '' ? null : t('console.queue.source', { source: row.sourceLabel });
}

// ——— payload readers ——————————————————————————————————————————————

export function isObligationVersion(kind: string): boolean {
  return kind === 'new_obligation_version';
}

/** The vocabulary and term kinds; a new record's kinds are neither this nor a version. */
export function isVocabularyKind(kind: string): boolean {
  return (VOCABULARY_KINDS as readonly string[]).includes(kind) || (TERM_KINDS as readonly string[]).includes(kind);
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
