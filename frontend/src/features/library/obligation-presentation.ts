import { byOrder, type KindRef, type PresentedPill, type VocabularyRef } from '@/features/shared/presentation-types';
import {
  applicabilityTone,
  complianceTone,
  slotTone,
  type ApplicabilityKind,
  type ComplianceKind,
} from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { formatDate, type FormatContext } from '@/shared/utils/format';

import type { ObligationProvenance, ObligationVersionRow, VersionConfirmation } from './types';

// Obligation row and header (design/system/pills-and-labels.md, slot order).
// Row: instrument, "Guidance" if not binding, applicability, compliance
// status if it applies, "Change waiting for approval", "N open changes".
// Header: instrument, regime, binding level, compliance status.
// Computed labels come from the message catalog with plural forms; the API
// sends `openChangeCount` and `changeWaitingForApproval`, never a phrase.

export interface ObligationFacts {
  /** The instrument's short name, e.g. "LVM". */
  instrument: VocabularyRef;
  regime?: VocabularyRef;
  binding: boolean;
  applicability?: KindRef<ApplicabilityKind>;
  /** Present only when the obligation applies and has been assessed. */
  complianceStatus?: KindRef<ComplianceKind>;
  changeWaitingForApproval?: boolean;
  openChangeCount?: number;
  libraryTags?: readonly VocabularyRef[];
  tenantTags?: readonly VocabularyRef[];
}

export type ObligationView = 'row' | 'header';

export const OBLIGATION_SLOT_ORDER = {
  instrument: 10,
  regime: 20,
  bindingLevel: 20,
  guidance: 20,
  applicability: 30,
  complianceStatus: 40,
  changeWaitingForApproval: 50,
  openChanges: 60,
  libraryTags: 70,
  tenantTags: 80,
} as const;

export function presentObligation(obligation: ObligationFacts, view: ObligationView, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    {
      key: `instrument:${obligation.instrument.key}`,
      label: obligation.instrument.label,
      tone: slotTone.instrument,
      order: OBLIGATION_SLOT_ORDER.instrument,
    },
  ];

  if (view === 'header') {
    if (obligation.regime !== undefined) {
      pills.push({
        key: `regime:${obligation.regime.key}`,
        label: obligation.regime.label,
        tone: slotTone.regime,
        order: OBLIGATION_SLOT_ORDER.regime,
      });
    }
    pills.push(presentBindingLevel(obligation.binding, OBLIGATION_SLOT_ORDER.bindingLevel + 1, t));
  } else {
    if (!obligation.binding) {
      pills.push({ key: 'guidance', label: t('pill.guidance'), tone: slotTone.guidance, order: OBLIGATION_SLOT_ORDER.guidance });
    }
    if (obligation.applicability !== undefined) {
      pills.push({
        key: `applicability:${obligation.applicability.key}`,
        label: obligation.applicability.label,
        tone: applicabilityTone[obligation.applicability.kind],
        order: OBLIGATION_SLOT_ORDER.applicability,
      });
    }
  }

  if (obligation.complianceStatus !== undefined) {
    pills.push({
      key: `compliance:${obligation.complianceStatus.key}`,
      label: obligation.complianceStatus.label,
      tone: complianceTone[obligation.complianceStatus.kind],
      order: OBLIGATION_SLOT_ORDER.complianceStatus,
    });
  }

  if (view === 'row') {
    if (obligation.changeWaitingForApproval === true) {
      pills.push({
        key: 'change-waiting-for-approval',
        label: t('pill.changeWaitingForApproval'),
        tone: slotTone.waitingForApproval,
        order: OBLIGATION_SLOT_ORDER.changeWaitingForApproval,
      });
    }
    const count = obligation.openChangeCount ?? 0;
    if (count > 0) {
      pills.push({
        key: 'open-changes',
        label: t('pill.openChanges', { count }),
        tone: slotTone.openChanges,
        order: OBLIGATION_SLOT_ORDER.openChanges,
      });
    }
    (obligation.libraryTags ?? []).forEach((tag, i) => {
      pills.push({ key: `library-tag:${tag.key}`, label: tag.label, tone: slotTone.libraryTag, order: OBLIGATION_SLOT_ORDER.libraryTags + i });
    });
    (obligation.tenantTags ?? []).forEach((tag, i) => {
      pills.push({
        key: `tenant-tag:${tag.key}`,
        label: tag.label,
        tone: slotTone.tenantTag,
        order: OBLIGATION_SLOT_ORDER.tenantTags + i,
        outlined: true,
      });
    });
  }

  return pills.sort(byOrder);
}

// A header's binding level (obligation and instrument cards): "Binding" is a
// neutral fact, "Guidance, comply or explain" needs attention.
export function presentBindingLevel(binding: boolean, order: number, t: Translate): PresentedPill {
  return binding
    ? { key: 'binding', label: t('pill.binding'), tone: slotTone.bindingLevel, order }
    : { key: 'guidance', label: t('pill.guidanceComplyOrExplain'), tone: slotTone.guidanceComplyOrExplain, order };
}

// Scope block, one dimension at a time: one brand pill per term; "All
// services" when every service is selected; plain text such as "Not
// client-specific" when the list is empty, because empty means no
// restriction. Dimensions are library rows, so one the catalog does not know
// yet lists its terms, or reads "Not specific" when empty.
export interface ScopeFacts {
  /** The dimension's stable key, e.g. "service_type". */
  dimension: string;
  terms: readonly VocabularyRef[];
  allSelected: boolean;
}

export interface PresentedScope {
  pills: PresentedPill[];
  plainText?: string;
}

const ALL_SELECTED: Readonly<Record<string, MessageKey>> = {
  service_type: 'pill.allServices',
};

const NOT_SPECIFIC: Readonly<Record<string, MessageKey>> = {
  regime: 'scope.notRegimeSpecific',
  legal_entity: 'scope.notEntitySpecific',
  service_type: 'scope.notServiceSpecific',
  client_category: 'scope.notClientSpecific',
  account_type: 'scope.notAccountSpecific',
  channel: 'scope.notChannelSpecific',
  lifecycle_stage: 'scope.notStageSpecific',
  jurisdiction: 'scope.notJurisdictionSpecific',
  licensed_activity: 'scope.notActivitySpecific',
  product_type: 'scope.notProductSpecific',
};

export function presentScope(scope: ScopeFacts, t: Translate): PresentedScope {
  if (scope.terms.length === 0) {
    return { pills: [], plainText: t(NOT_SPECIFIC[scope.dimension] ?? 'scope.notSpecific') };
  }
  const all = ALL_SELECTED[scope.dimension];
  if (scope.allSelected && all !== undefined) {
    return { pills: [{ key: 'scope:all', label: t(all), tone: slotTone.scopeTerm, order: 0 }] };
  }
  return { pills: scope.terms.map((term, i) => ({ key: `scope:${term.key}`, label: term.label, tone: slotTone.scopeTerm, order: i })) };
}

// "Outside your scope: Advice" in the meta line of a row that only shows
// with "Show outside footprint": the terms that put it outside.
export function outsideFootprintLabel(terms: readonly VocabularyRef[], t: Translate): string {
  return t('library.outsideFootprint', { terms: terms.map((term) => term.label).join(', ') });
}

// "Change pending: in force 1 Oct" on a scope facet whose applicability is
// waiting for approval. The caller formats the date with formatDate().
export function presentChangePending(formattedDate: string, t: Translate): PresentedPill {
  return { key: 'change-pending', label: t('pill.changePending', { date: formattedDate }), tone: slotTone.changePending, order: 0 };
}

// "Machine-confirmed 17 Aug 2026: proposed by watch-sweeper, confirmed by
// library-confirmer", read where a person's approval or verification would be
// (INV-05, INV-06, PRO-02, D-74); null means the person wording stands. It
// follows who confirmed alone, never which agents are named, since a person
// may propose what an agent confirms. `stamp` is the record's re-verification
// for the "Last verified" slot: the label gives way only to one a named person
// made after that approval, never to a seeded date nobody signed. A version
// row passes null, because who approved a version does not change when
// somebody later checks the record. An inventory row passes its own version
// in force and stamp, so the list follows the same rule as the card.
export function machineConfirmedLabel(
  version: Pick<ObligationVersionRow, 'approvedAt' | keyof VersionConfirmation> | null,
  stamp: Pick<ObligationProvenance, 'lastVerifiedAt' | 'verifiedBy'> | null,
  t: Translate,
  ctx: FormatContext,
): string | null {
  if (version === null || version.verifiedOrigin !== 'agent' || version.approvedAt === null) return null;
  const personSawItLater =
    stamp !== null && stamp.verifiedBy !== null && stamp.lastVerifiedAt !== null && Date.parse(stamp.lastVerifiedAt) > Date.parse(version.approvedAt);
  if (personSawItLater) return null;
  const date = formatDate(version.approvedAt, ctx);
  const confirmer = version.confirmedByAgent?.key ?? '';
  return version.proposedByAgent === null
    ? t('inventory.obligation.machineConfirmedBy', { date, confirmer })
    : t('inventory.obligation.machineConfirmed', { date, proposer: version.proposedByAgent.key, confirmer });
}
