import type { PillTone } from '@/components/ui/pill-tones';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { proposalStatusTone, slotTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { STEP_UP_REQUIRED_CODE } from '@/shared/utils/api-client';
import { NETWORK_PROBLEM_CODE, problemFrom } from '@/shared/utils/problem';

import {
  TERM_KINDS,
  VOCABULARY_KINDS,
  type InstrumentPayload,
  type NewObligationPayload,
  type ObligationVersionPayload,
  type ProposalKind,
  type ProposalQueueRow,
  type ProposalRow,
  type ProposalStatus,
  type VocabularyProposalPayload,
} from './types';

// Pills and derived facts for the console queue (design/screens/console-queue.html;
// PRO-01, PRO-02, PRO-03, AC-PRO2). Tone is never chosen by a person: the kind pill
// sits in the same slot a change type does (notice), the status pill's tone comes
// from the fixed status kind, and "Yours" is the server's `isMine` in the `you` slot
// (positive). An agent that decided or corrected a proposal is named as an agent,
// never in a person's slot, and its decision reads as machine-confirmed.

const SLOT_ORDER = { kind: 10, status: 20, flagged: 25, yours: 30 } as const;

const KIND_LABEL: Readonly<Record<ProposalKind, MessageKey>> = {
  new_instrument: 'console.queue.kind.newInstrument',
  new_instrument_summary: 'console.queue.kind.newInstrumentSummary',
  new_translations: 'console.queue.kind.newTranslations',
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
  obligation_scope: 'console.queue.kind.retag',
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

export function presentProposal(row: Pick<ProposalQueueRow, 'kind' | 'status' | 'isMine' | 'riskFlags'>, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: 'kind', label: kindLabel(row.kind, t), tone: slotTone.proposalKind, order: SLOT_ORDER.kind },
    { key: 'status', label: statusLabel(row.status, t), tone: statusTone(row.status), order: SLOT_ORDER.status },
  ];
  // AGT-07: the injection screen flagged a text the proposal arrived with; only a person decides it.
  if ((row.riskFlags ?? []).length > 0) pills.push({ key: 'flagged', label: t('console.queue.flagged'), tone: slotTone.riskFlagged, order: SLOT_ORDER.flagged });
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

/**
 * Why a waiting row cannot be approved together with others, or null when it can: it is
 * open, one record, not the reader's own, and nothing in it was flagged. A flagged
 * proposal is opened and read before anyone approves it (AGT-07); the reader's own needs
 * someone else (AC-PRO2); a batch is decided row by row on its own screen (PRO-04).
 */
export function selectionBlock(row: Pick<ProposalQueueRow, 'status' | 'isBatch' | 'isMine' | 'riskFlags'>, t: Translate): string | null {
  if (row.status !== 'open') return t('console.queue.select.blocked.decided');
  if (row.isBatch === true) return t('console.queue.select.blocked.batch');
  if (row.isMine === true) return t('console.queue.select.blocked.mine');
  if ((row.riskFlags ?? []).length > 0) return t('console.queue.select.blocked.flagged');
  return null;
}

/** Why the server refused one approval of many: the passkey not given, the network, or the server's own sentence (branching on `code`, never on `detail`). */
export function refusalReason(error: unknown, t: Translate): string {
  const problem = problemFrom(error);
  if (problem === null) return t('problem.generic');
  if (problem.code === STEP_UP_REQUIRED_CODE) return t('console.queue.approveMany.passkeyNotGiven');
  if (problem.code === NETWORK_PROBLEM_CODE) return t('problem.network');
  return problem.detail === '' ? t('problem.generic') : problem.detail;
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

/** A new record's payload, read by its kind; null for any other kind or a payload without its titles. */
function newRecordPayloadOf(row: Pick<ProposalRow, 'kind' | 'payload'>, kind: ProposalKind): Record<string, unknown> | null {
  const payload = (row.payload ?? {}) as Record<string, unknown>;
  return row.kind === kind && typeof payload.titles === 'object' && payload.titles !== null ? payload : null;
}

export function instrumentPayloadOf(row: Pick<ProposalRow, 'kind' | 'payload'>): InstrumentPayload | null {
  return newRecordPayloadOf(row, 'new_instrument') as InstrumentPayload | null;
}

/** A `new_instrument_summary` payload: the instrument it describes by key and its text per language (INV-09). */
export interface InstrumentSummaryPayload {
  instrument: string;
  summaries: Record<string, string>;
  originalLanguage: string;
  isMachine?: boolean;
}

export function instrumentSummaryPayloadOf(row: Pick<ProposalRow, 'kind' | 'payload'>): InstrumentSummaryPayload | null {
  const payload = (row.payload ?? {}) as Record<string, unknown>;
  return row.kind === 'new_instrument_summary' && typeof payload.summaries === 'object' && payload.summaries !== null ? (payload as unknown as InstrumentSummaryPayload) : null;
}

/** A `new_translations` payload: one record's machine translations per language, and the language of each original (D-129). */
export interface TranslationsPayload {
  target: string;
  key: string;
  titles: Record<string, string>;
  titlesFrom?: string;
  summaries: Record<string, string>;
  summariesFrom?: string;
}

export function translationsPayloadOf(row: Pick<ProposalRow, 'kind' | 'payload'>): TranslationsPayload | null {
  const payload = (row.payload ?? {}) as Record<string, unknown>;
  if (row.kind !== 'new_translations' || typeof payload.key !== 'string') return null;
  const texts = (value: unknown) => (typeof value === 'object' && value !== null ? (value as Record<string, string>) : {});
  return { ...(payload as unknown as TranslationsPayload), titles: texts(payload.titles), summaries: texts(payload.summaries) };
}

export function newObligationPayloadOf(row: Pick<ProposalRow, 'kind' | 'payload'>): NewObligationPayload | null {
  return newRecordPayloadOf(row, 'new_obligation') as NewObligationPayload | null;
}

/** A `new_provision` or `new_provision_version` payload: the law's own words per language (D-142). */
export interface ProvisionPayload {
  /** The structure of a new provision; a new version of one carries none of it. */
  key?: string;
  instrument?: string;
  parent?: string | null;
  provisionKind?: string;
  refLabel?: string;
  heading?: string;
  texts: Record<string, string>;
  /** The language the authority published the text in, which governs. */
  originalLanguage: string;
  /** The other languages the authority itself published, such as a Finnish act's Swedish. */
  officialLanguages?: string[] | null;
  isMachine?: boolean;
  /** The stable keys of the obligations approval ties the provision to. */
  obligations?: string[] | null;
  effectiveFrom?: string | null;
  effectiveFromPrecision?: string;
}

export function provisionPayloadOf(row: Pick<ProposalRow, 'kind' | 'payload'>): ProvisionPayload | null {
  const payload = (row.payload ?? {}) as Record<string, unknown>;
  const kind = row.kind === 'new_provision' || row.kind === 'new_provision_version';
  return kind && typeof payload.texts === 'object' && payload.texts !== null ? (payload as unknown as ProvisionPayload) : null;
}

export interface LanguageText {
  language: string;
  text: string;
  /**
   * `original` for the language the authority published in, `official` for one it also
   * published in, `machine` for a machine translation (AUD-02), else `none`.
   */
  mark: 'original' | 'official' | 'machine' | 'none';
}

export interface LanguageMarks {
  /** Every text but the original is a machine translation. */
  isMachine?: boolean;
  /** Languages the authority itself published beside the original. */
  officialLanguages?: readonly string[] | null;
  /**
   * The texts are bleqq's own wording, a duty's title or a summary: the language they were
   * written in comes first but is never called the original, which only the rule's own
   * words and the authority's name have (D-142).
   */
  bleqqWording?: boolean;
}

/**
 * A text per language, each marked for what it is: the one written first, then any the
 * authority itself published, then the rest, each group alphabetically.
 */
export function languageTexts(texts: Readonly<Record<string, string>>, originalLanguage: string, marks: LanguageMarks = {}): LanguageText[] {
  const official = (language: string) => marks.officialLanguages?.includes(language) === true;
  const markOf = (language: string): LanguageText['mark'] => {
    if (language === originalLanguage) return marks.bleqqWording === true ? 'none' : 'original';
    if (official(language)) return 'official';
    return marks.isMachine === true ? 'machine' : 'none';
  };
  const rank = (language: string) => (language === originalLanguage ? 0 : official(language) ? 1 : 2);
  return Object.entries(texts)
    .map(([language, text]): LanguageText => ({ language, text, mark: markOf(language) }))
    .sort((a, b) => rank(a.language) - rank(b.language) || a.language.localeCompare(b.language));
}

const MARK_LABEL: Readonly<Record<Exclude<LanguageText['mark'], 'none'>, MessageKey>> = {
  original: 'console.queue.detail.languageOriginal',
  official: 'console.queue.detail.languageOfficial',
  machine: 'console.queue.detail.languageMachine',
};

/** The line above a text: its language's name, and what it is when it is the original, an official text or a machine translation. */
export function languageTextLabel(mark: LanguageText['mark'], language: string, t: Translate): string {
  return mark === 'none' ? language : t(MARK_LABEL[mark], { language });
}

/** The label of `key` in a list read from its own rows, or the key itself while the list is loading or holds no such row. */
export function labelOfKey(rows: readonly { key: string; label: string }[] | undefined, key: string): string {
  return rows?.find((row) => row.key === key)?.label ?? key;
}

/** Whether a new instrument binds: yes, no, or left to its level's default (schemas.py `ProposalInstrumentPayload.binding`). */
export function bindingLabel(binding: boolean | null | undefined, t: Translate): string {
  if (binding === true) return t('console.queue.detail.binding.yes');
  if (binding === false) return t('console.queue.detail.binding.no');
  return t('console.queue.detail.binding.levelDefault');
}

// Every field a proposal sources (backend/apps/proposals/logic.py `sourced_fields`), named in
// words and listed in this order: where the record sits, its names and texts, how it is
// cited, how it is classed, when it binds, its scope, and what it implements. A text field
// is sourced per language (`titles.sv`), so its label names the language.
const FIELD_LABEL = {
  instrument: 'console.queue.field.instrument',
  parent: 'console.queue.field.parent',
  sortOrder: 'console.queue.field.sortOrder',
  titles: 'console.queue.field.title',
  summaries: 'console.queue.field.text',
  texts: 'console.queue.field.legalText',
  shortName: 'console.queue.field.shortName',
  officialRef: 'console.queue.field.officialRef',
  refLabel: 'console.queue.field.refLabel',
  heading: 'console.queue.field.heading',
  provisionKind: 'console.queue.field.provisionKind',
  eliUri: 'console.queue.field.eliUri',
  level: 'console.queue.field.level',
  binding: 'console.queue.field.binding',
  jurisdiction: 'console.queue.field.jurisdiction',
  authority: 'console.queue.field.authority',
  regime: 'console.queue.field.regime',
  dutyType: 'console.queue.field.dutyType',
  effectiveFrom: 'console.queue.field.effectiveFrom',
  inForceFrom: 'console.queue.field.inForceFrom',
  inForceTo: 'console.queue.field.inForceTo',
  terms: 'console.queue.field.scope',
  obligations: 'console.queue.field.obligations',
  implementsNote: 'console.queue.field.implementsNote',
} as const satisfies Record<string, MessageKey>;

type SourcedField = keyof typeof FIELD_LABEL;

const FIELD_ORDER = Object.keys(FIELD_LABEL);

function isSourcedField(name: string): name is SourcedField {
  return name in FIELD_LABEL;
}

/** `titles.sv` belongs to `titles`; a field with no language is its own group. */
function groupOf(field: string): string {
  const dot = field.indexOf('.');
  return dot === -1 ? field : field.slice(0, dot);
}

/** The per-field source panel beside "What changes": one line per field the proposal sources, in words. */
export function fieldSourceLabel(field: string, languageName: (code: string) => string, t: Translate): string {
  const group = groupOf(field);
  if (!isSourcedField(group)) return field;
  return group === field ? t(FIELD_LABEL[group]) : t(FIELD_LABEL[group], { language: languageName(field.slice(group.length + 1)) });
}

function fieldRank(field: string): number {
  const index = FIELD_ORDER.indexOf(groupOf(field));
  return index === -1 ? FIELD_ORDER.length : index;
}

/** `fieldSources` as ordered `{field, url}` rows in the fixed order above, a text's languages alphabetically, anything else last. */
export function fieldSourceRows(fieldSources: Record<string, string>): { field: string; url: string }[] {
  return Object.entries(fieldSources)
    .map(([field, url]) => ({ field, url }))
    .sort((a, b) => fieldRank(a.field) - fieldRank(b.field) || a.field.localeCompare(b.field));
}

/**
 * The field sources grouped by page, in the fields' own order: one row per page with every
 * field it is the source of, so a page that supports every fact is named once, not per field.
 */
export function fieldSourceGroups(fieldSources: Record<string, string>): { url: string; fields: string[] }[] {
  const groups = new Map<string, string[]>();
  for (const { field, url } of fieldSourceRows(fieldSources)) {
    groups.set(url, [...(groups.get(url) ?? []), field]);
  }
  return [...groups].map(([url, fields]) => ({ url, fields }));
}

/** The proposed scope as `brand` pills, in the scope block's own slot (pills-and-labels.md). */
export function scopeTermPills(refs: readonly string[], labelOf: (ref: string) => string): PresentedPill[] {
  return refs.map((ref, index) => ({ key: `term:${ref}`, label: labelOf(ref), tone: slotTone.scopeTerm, order: index }));
}
