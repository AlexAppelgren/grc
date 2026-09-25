import type { PillTone } from '@/components/ui/pill-tones';
import { pillToneNames } from '@/components/ui/pill-tones';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { complianceTone, proposalStatusTone, severityTone, slotTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { problemFrom } from '@/shared/utils/problem';

import type { NearDuplicateCandidate, ProposalRef, VocabularyListSummary, VocabularyRow } from './types';

// Pills and derived facts for the vocabulary screens
// (design/screens/admin-vocabularies.html, admin-vocabulary.html; VOC-01,
// VOC-02). Tone is never chosen by a person: it comes from the list's slot
// (a change type is notice, a flag or library tag brand, a tenant tag an
// outlined information pill) or from the fixed kind or tone the row carries
// (urgency by its tone field, a compliance status by its category). A label
// never decides anything.

export const NEAR_DUPLICATE_CODE = 'near_duplicate';
/** 409: the same label once case and surrounding space are set aside; `force` cannot override it. */
export const DUPLICATE_KEY_CODE = 'duplicate_key';
export const IN_USE_CODE = 'in_use';
export const SYSTEM_ROW_CODE = 'system_row';

// Lists whose keys the reference seed alone files and nothing merges away (D-94): a
// proposal relabels, retires or restores one of their values, a seeded one included.
const FIXED_KEY_LISTS: ReadonlySet<string> = new Set(['jurisdiction']);

export function hasFixedKeys(list: string): boolean {
  return FIXED_KEY_LISTS.has(list);
}

export interface ValueTone {
  tone: PillTone;
  outlined: boolean;
}

export type VocabularyValueFacts = Pick<VocabularyRow, 'key' | 'kind' | 'label' | 'extra'>;
export type VocabularyRowFacts = Pick<VocabularyRow, 'active' | 'isSystem' | 'isDefault'>;

// Lists whose values sit in a fixed slot of the design (pills-and-labels.md,
// "Where tone comes from"). Anything not listed is a neutral fact.
const slotByList: Readonly<Record<string, PillTone>> = {
  change_type: slotTone.changeType,
  flag: slotTone.flag,
  library_tag: slotTone.libraryTag,
  taxonomy_term: slotTone.scopeTerm,
  term_dimension: slotTone.scopeTerm,
  instrument_level: slotTone.bindingLevel,
  source_kind: slotTone.source,
  tenant_tag: slotTone.tenantTag,
};

const OUTLINED_LISTS: ReadonlySet<string> = new Set(['tenant_tag']);

function isPillTone(value: unknown): value is PillTone {
  return typeof value === 'string' && (pillToneNames as readonly string[]).includes(value);
}

function kindTone(list: string, kind: string | null): PillTone | null {
  if (kind === null) return null;
  if (list === 'compliance_status') return complianceTone[kind as keyof typeof complianceTone] ?? null;
  if (list === 'risk_rating') return severityTone[kind as keyof typeof severityTone] ?? null;
  return null;
}

export function valueTone(list: string, row: VocabularyValueFacts): ValueTone {
  const outlined = OUTLINED_LISTS.has(list);
  // A row that carries a tone (urgency) decides; a tone outside the six is ignored.
  if (list === 'urgency') return { tone: isPillTone(row.extra.tone) ? row.extra.tone : 'information', outlined };
  const byKind = kindTone(list, row.kind);
  if (byKind !== null) return { tone: byKind, outlined };
  return { tone: slotByList[list] ?? 'information', outlined };
}

export function presentVocabularyValue(list: string, row: VocabularyValueFacts): PresentedPill {
  const { tone, outlined } = valueTone(list, row);
  return { key: `value:${row.key}`, label: row.label, tone, order: 0, outlined };
}

const ORDER = { system: 10, default: 20, status: 50 } as const;

export function presentVocabularyRow(list: string, row: VocabularyRowFacts, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [];
  if (row.isSystem) pills.push({ key: 'row:system', label: t('admin.vocabularies.systemValue'), tone: 'information', order: ORDER.system });
  if (row.isDefault) pills.push({ key: 'row:default', label: t('admin.vocabularies.defaultValue'), tone: 'information', order: ORDER.default });
  if (!row.active) pills.push({ key: 'row:retired', label: t('admin.vocabularies.retired'), tone: 'information', order: ORDER.status });
  void list;
  return pills.sort(byOrder);
}

export function usageText(count: number, t: Translate): string {
  return count === 0 ? t('admin.vocabularies.notUsed') : t('admin.vocabularies.usedBy', { count });
}

// Near matches for the picker and the add form: an exact match ignoring case
// and surrounding space comes first, then prefixes, then bigram overlap for
// typos ("Custdy" finds "Custody"). Retired values are never offered.
function normalise(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, ' ');
}

function bigrams(text: string): Set<string> {
  const padded = ` ${text} `;
  const set = new Set<string>();
  for (let i = 0; i < padded.length - 1; i += 1) set.add(padded.slice(i, i + 2));
  return set;
}

export function similarity(a: string, b: string): number {
  const x = bigrams(normalise(a));
  const y = bigrams(normalise(b));
  if (x.size === 0 || y.size === 0) return 0;
  let shared = 0;
  for (const gram of x) if (y.has(gram)) shared += 1;
  return (2 * shared) / (x.size + y.size);
}

const NEAR_MATCH_FLOOR = 0.45;

export interface NearMatchResult<T> {
  exact: T | null;
  matches: T[];
}

export function nearMatches<T extends Pick<VocabularyRow, 'key' | 'label' | 'active'>>(query: string, rows: readonly T[]): NearMatchResult<T> {
  const active = rows.filter((row) => row.active);
  const needle = normalise(query);
  if (needle === '') return { exact: null, matches: [...active] };
  const scored = active
    .map((row) => {
      const label = normalise(row.label);
      const score = label === needle ? 3 : label.startsWith(needle) || needle.startsWith(label) ? 2 : label.includes(needle) ? 1.5 : similarity(needle, label);
      return { row, score };
    })
    .filter(({ score }) => score >= NEAR_MATCH_FLOOR)
    .sort((a, b) => b.score - a.score);
  const exact = scored.find(({ score }) => score === 3)?.row ?? null;
  return { exact, matches: scored.map(({ row }) => row) };
}

function candidateOf(value: unknown): NearDuplicateCandidate | null {
  if (typeof value !== 'object' || value === null) return null;
  const record = value as Record<string, unknown>;
  if (typeof record.key !== 'string' || typeof record.label !== 'string') return null;
  return { key: record.key, label: record.label, ...(typeof record.similarity === 'number' ? { similarity: record.similarity } : {}) };
}

// The server refuses a new value in two ways, each naming the value that
// is already there (apps/taxonomy/tenant_lists_logic.py): 409 duplicate_key
// for the same label ("custody " for "Custody"), 422 near_duplicate for a
// close one ("Custdy"). The screens say the first as a fact and ask the
// second as a question (design/screens/states.html, admin-vocabulary.html).
function candidatesOf(error: unknown, code: string): NearDuplicateCandidate[] | null {
  const problem = problemFrom(error);
  if (problem === null || problem.code !== code) return null;
  const body = (error as { response?: { data?: unknown } }).response?.data;
  const record = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
  const raw = Array.isArray(record.candidates) ? record.candidates : Array.isArray(record.errors) ? record.errors : [];
  return raw.map(candidateOf).filter((c): c is NearDuplicateCandidate => c !== null);
}

/** The candidates of a `near_duplicate` refusal, whether the server lists them as `candidates` or `errors`; null for any other error. */
export function nearDuplicateFrom(error: unknown): NearDuplicateCandidate[] | null {
  return candidatesOf(error, NEAR_DUPLICATE_CODE);
}

/** The value a `duplicate_key` refusal names; null for any other error. */
export function exactDuplicateFrom(error: unknown): NearDuplicateCandidate[] | null {
  return candidatesOf(error, DUPLICATE_KEY_CODE);
}

// The list names the API uses are keys; their titles come from the catalog
// so a list an admin has never seen still reads as a phrase. A list the
// catalog does not know yet reads as its key in plain words.
// Exported so a test can prove every key resolves in every catalog (chunk4-T20), without
// a second, hand-kept list of list names that would drift from this one.
export const listTitle: Readonly<Record<string, MessageKey>> = {
  tenant_tag: 'admin.vocabularies.list.tenant_tag',
  tenant_role: 'admin.vocabularies.list.tenant_role',
  compliance_status: 'admin.vocabularies.list.compliance_status',
  risk_rating: 'admin.vocabularies.list.risk_rating',
  case_sub_status: 'admin.vocabularies.list.case_sub_status',
  dismissal_reason: 'admin.vocabularies.list.dismissal_reason',
  close_reason: 'admin.vocabularies.list.close_reason',
  link_kind: 'admin.vocabularies.list.link_kind',
  effort_size: 'admin.vocabularies.list.effort_size',
  change_type: 'admin.vocabularies.list.change_type',
  urgency: 'admin.vocabularies.list.urgency',
  flag: 'admin.vocabularies.list.flag',
  library_tag: 'admin.vocabularies.list.library_tag',
  taxonomy_term: 'admin.vocabularies.list.taxonomy_term',
  term_dimension: 'admin.vocabularies.list.term_dimension',
  duty_type: 'admin.vocabularies.list.duty_type',
  instrument_level: 'admin.vocabularies.list.instrument_level',
  provision_kind: 'admin.vocabularies.list.provision_kind',
  relation_type: 'admin.vocabularies.list.relation_type',
  source_kind: 'admin.vocabularies.list.source_kind',
  jurisdiction: 'admin.vocabularies.list.jurisdiction',
  language: 'admin.vocabularies.list.language',
  // PRO-01: the reasons a proposal is rejected for, a library vocabulary list without a
  // kind since chunk4-T2 (docs/plans/briefs/CHUNK4_TASKS.md "DEFAULTS TAKEN"). The keys
  // are written beside every other list's here by chunk4-T14, the first task that
  // renders the list, in this file's own catalog pair rather than console/{en,sv}.json
  // (T14's nominal owned path for them): every other `admin.vocabularies.list.*` and
  // `.marker.*` key lives here, and a lone pair in a different file would drift from
  // that convention for no reason next to it.
  rejection_reason: 'admin.vocabularies.list.rejection_reason',
};

export const listMarker: Readonly<Record<string, MessageKey>> = {
  tenant_tag: 'admin.vocabularies.marker.tenant_tag',
  tenant_role: 'admin.vocabularies.marker.tenant_role',
  compliance_status: 'admin.vocabularies.marker.compliance_status',
  risk_rating: 'admin.vocabularies.marker.risk_rating',
  case_sub_status: 'admin.vocabularies.marker.case_sub_status',
  dismissal_reason: 'admin.vocabularies.marker.reason',
  close_reason: 'admin.vocabularies.marker.reason',
  link_kind: 'admin.vocabularies.marker.link_kind',
  effort_size: 'admin.vocabularies.marker.effort_size',
  change_type: 'admin.vocabularies.marker.change_type',
  urgency: 'admin.vocabularies.marker.urgency',
  flag: 'admin.vocabularies.marker.flag',
  library_tag: 'admin.vocabularies.marker.library_tag',
  taxonomy_term: 'admin.vocabularies.marker.taxonomy_term',
  term_dimension: 'admin.vocabularies.marker.term_dimension',
  duty_type: 'admin.vocabularies.marker.duty_type',
  instrument_level: 'admin.vocabularies.marker.instrument_level',
  provision_kind: 'admin.vocabularies.marker.provision_kind',
  relation_type: 'admin.vocabularies.marker.relation_type',
  source_kind: 'admin.vocabularies.marker.source_kind',
  jurisdiction: 'admin.vocabularies.marker.jurisdiction',
  language: 'admin.vocabularies.marker.language',
  rejection_reason: 'admin.vocabularies.marker.rejection_reason',
};

export function humaniseListKey(list: string): string {
  return list.replace(/[._:-]/g, ' ');
}

export function listLabel(list: string, t: Translate): string {
  const key = listTitle[list];
  return key === undefined ? humaniseListKey(list) : t(key);
}

export function isLibraryList(summary: Pick<VocabularyListSummary, 'tier'>): boolean {
  return summary.tier === 'library';
}

// One marker pill per list in the list's own slot tone, so an admin sees the
// tone before opening it, plus the computed "N suggestions" when any wait.
export function presentListSummary(summary: VocabularyListSummary, t: Translate): PresentedPill[] {
  const markerKey = listMarker[summary.list];
  const label = markerKey === undefined ? humaniseListKey(summary.list) : t(markerKey);
  const { tone, outlined } = valueTone(summary.list, { key: summary.list, kind: null, label, extra: {} });
  const pills: PresentedPill[] = [{ key: `list:${summary.list}`, label, tone, order: 0, outlined }];
  const pending = summary.pendingSuggestions ?? 0;
  if (pending > 0) pills.push({ key: 'list:suggestions', label: t('admin.vocabularies.suggestions', { count: pending }), tone: slotTone.waitingForApproval, order: 10 });
  return pills;
}

// A key from a typed label: lower case, ASCII letters and digits, underscores.
export function keyFromLabel(label: string): string {
  return label
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export function changeSummary(proposal: Pick<ProposalRef, 'title'>, t: Translate): string {
  return t('admin.vocabularies.proposed', { title: proposal.title });
}

/** A proposal this bank made on a library list and is still waiting on: the open status's tone. */
export function presentPendingProposal(t: Translate): PresentedPill[] {
  return [{ key: 'proposal:open', label: t('admin.vocabulary.waitingForReview'), tone: proposalStatusTone.open, order: 0 }];
}

/** A value suggested from a picker (VOC-03), marked on the field while it waits for an administrator. */
export function presentSuggestedValue(label: string, t: Translate): PresentedPill[] {
  return [{ key: 'suggestion:pending', label: t('picker.suggested', { label }), tone: proposalStatusTone.open, order: 0 }];
}
