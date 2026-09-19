import { byOrder, type KindRef, type PresentedPill, type VocabularyRef } from '@/features/shared/presentation-types';
import {
  applicabilityTone,
  complianceTone,
  slotTone,
  type ApplicabilityKind,
  type ComplianceKind,
} from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';

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
    pills.push({
      key: obligation.binding ? 'binding' : 'guidance',
      label: obligation.binding ? t('pill.binding') : t('pill.guidanceComplyOrExplain'),
      tone: slotTone.bindingLevel,
      order: OBLIGATION_SLOT_ORDER.bindingLevel + 1,
    });
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

// Scope block: one brand pill per term; "All services" when every term is
// selected; plain text "Not client-specific" when the list is empty, because
// empty means no restriction.
export interface PresentedScope {
  pills: PresentedPill[];
  plainText?: string;
}

export function presentScope(terms: readonly VocabularyRef[], allSelected: boolean, t: Translate): PresentedScope {
  if (allSelected) {
    return { pills: [{ key: 'all', label: t('pill.allServices'), tone: slotTone.scopeTerm, order: 0 }] };
  }
  if (terms.length === 0) {
    return { pills: [], plainText: t('scope.notClientSpecific') };
  }
  return { pills: terms.map((term, i) => ({ key: `scope:${term.key}`, label: term.label, tone: slotTone.scopeTerm, order: i })) };
}

// "Change pending: in force 1 Oct" on a scope facet whose applicability is
// waiting for approval. The caller formats the date with formatDate().
export function presentChangePending(formattedDate: string, t: Translate): PresentedPill {
  return { key: 'change-pending', label: t('pill.changePending', { date: formattedDate }), tone: slotTone.changePending, order: 0 };
}
