import type { PresentedPill } from '@/features/shared/presentation-types';
import { proposalStatusTone, slotTone, type ProposalStatusKind } from '@/features/shared/tone-by-kind';
import { languageName } from '@/features/library/version-presentation';
import type { MessageKey, Translate } from '@/shared/i18n';
import { externalHref } from '@/shared/utils/external-href';
import { formatDate, type FormatContext } from '@/shared/utils/format';

import type { PrivateProposalRow } from './types';

// The bank's own queue (design/screens/tenant-private-records.html; OWN-03, PRO-03).
// A row's pills are, in order, the kind (notice), the status (Waiting warning, Approved
// positive, Rejected and Superseded information) and, when the bank's own agent filed it,
// "Proposed by our agent" (brand, the tone of an agent version). A person proposer is meta
// text. The API sends kinds and keys, never a phrase.

const KIND_LABEL: Readonly<Record<string, MessageKey>> = {
  new_instrument: 'privateRecords.kind.newInstrument',
  new_obligation: 'privateRecords.kind.newObligation',
  new_obligation_version: 'privateRecords.kind.newVersion',
};

const STATUS_LABEL: Readonly<Record<ProposalStatusKind, MessageKey>> = {
  open: 'privateRecords.status.open',
  approved: 'privateRecords.status.approved',
  rejected: 'privateRecords.status.rejected',
  superseded: 'privateRecords.status.superseded',
};

function isStatus(status: string): status is ProposalStatusKind {
  return status in STATUS_LABEL;
}

export function presentPrivateProposal(row: Pick<PrivateProposalRow, 'kind' | 'status' | 'origin'>, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [{ key: `kind:${row.kind}`, label: t(KIND_LABEL[row.kind] ?? 'privateRecords.kind.other'), tone: slotTone.proposalKind, order: 10 }];
  if (isStatus(row.status)) {
    pills.push({ key: `status:${row.status}`, label: t(STATUS_LABEL[row.status]), tone: proposalStatusTone[row.status], order: 20 });
  }
  if (row.origin === 'agent') {
    pills.push({ key: 'proposed-by-agent', label: t('privateRecords.proposedByAgent'), tone: slotTone.ownAgentProposal, order: 30 });
  }
  return pills;
}

/** Who filed it, as meta text: null for the bank's own agent, which the row's pill names. */
export function proposerLine(row: Pick<PrivateProposalRow, 'origin' | 'isMine'>, t: Translate): string | null {
  if (row.origin === 'agent') return null;
  return row.isMine ? t('privateRecords.proposedByYou') : t('privateRecords.proposedByColleague');
}

/** A source's host without "www.", or null when the address is not a link (H26). */
export function sourceHost(url: string): string | null {
  return externalHref(url) === null ? null : new URL(url).hostname.replace(/^www\./, '');
}

/** Every distinct source the proposal names, the record's own first, so each field can point at one by number. */
export function sourcesOf(row: Pick<PrivateProposalRow, 'sourceUrl' | 'fieldSources'>): string[] {
  return [...new Set([row.sourceUrl ?? '', ...Object.values(row.fieldSources ?? {})])].filter((url) => url !== '');
}

export interface PayloadRow {
  /** The payload path its source is filed under, e.g. `titles.sv` or `dutyType`. */
  field: string;
  label: string;
  value: string;
  /** The number of its source in `sourcesOf`, or null when none was filed for it. */
  source: number | null;
  /** The content language of a text field, for the `lang` attribute. */
  language?: string;
}

// The payload fields the reviewer checks, in the card's order; keys and language flags are
// left out. `titles` and `summaries` hold one text per content language.
const FIELD_LABEL = {
  titles: 'privateRecords.field.titles',
  shortName: 'privateRecords.field.shortName',
  officialRef: 'privateRecords.field.officialRef',
  refLabel: 'privateRecords.field.refLabel',
  summaries: 'privateRecords.field.summaries',
  originalLanguage: 'privateRecords.field.originalLanguage',
  instrument: 'privateRecords.field.instrument',
  level: 'privateRecords.field.level',
  jurisdiction: 'privateRecords.field.jurisdiction',
  authority: 'privateRecords.field.authority',
  regime: 'privateRecords.field.regime',
  dutyType: 'privateRecords.field.dutyType',
  inForceFrom: 'privateRecords.field.inForceFrom',
  inForceTo: 'privateRecords.field.inForceTo',
  effectiveFrom: 'privateRecords.field.effectiveFrom',
  terms: 'privateRecords.field.terms',
} as const satisfies Record<string, MessageKey>;
const TEXT_FIELDS: ReadonlySet<string> = new Set(['titles', 'summaries']);
const DATE_FIELDS: ReadonlySet<string> = new Set(['inForceFrom', 'inForceTo', 'effectiveFrom']);

function shownValue(field: string, value: unknown, ctx: FormatContext): string {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string').join(', ');
  if (typeof value !== 'string') return '';
  if (field === 'originalLanguage') return languageName(value, ctx.locale);
  return DATE_FIELDS.has(field) ? formatDate(value, ctx) : value;
}

/** What the proposal adds, one row per field it sets, each beside the number of its source. */
export function payloadRows(row: Pick<PrivateProposalRow, 'payload' | 'fieldSources' | 'sourceUrl'>, t: Translate, ctx: FormatContext): PayloadRow[] {
  const payload = row.payload ?? {};
  const sources = sourcesOf(row);
  const fieldSources = row.fieldSources ?? {};
  const numberOf = (field: string): number | null => {
    const index = sources.indexOf(fieldSources[field] ?? '');
    return index === -1 ? null : index + 1;
  };
  const rows: PayloadRow[] = [];
  for (const [field, labelKey] of Object.entries(FIELD_LABEL)) {
    const value = payload[field];
    if (TEXT_FIELDS.has(field)) {
      if (typeof value !== 'object' || value === null) continue;
      for (const [language, text] of Object.entries(value)) {
        if (typeof text !== 'string' || text === '') continue;
        const path = `${field}.${language}`;
        rows.push({ field: path, label: t(labelKey, { language: languageName(language, ctx.locale) }), value: text, source: numberOf(path), language });
      }
      continue;
    }
    const shown = shownValue(field, value, ctx);
    if (shown !== '') rows.push({ field, label: t(labelKey), value: shown, source: numberOf(field) });
  }
  return rows;
}
