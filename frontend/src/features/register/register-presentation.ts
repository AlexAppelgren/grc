import { OBLIGATION_SLOT_ORDER } from '@/features/library/obligation-presentation';
import { byOrder, type KindRef, type PresentedPill, type VocabularyRef } from '@/features/shared/presentation-types';
import {
  applicabilityTone,
  complianceTone,
  gapTone,
  riskTone,
  severityTone,
  slotTone,
  type ApplicabilityKind,
  type ComplianceKind,
  type GapKind,
  type RiskKind,
  type SeverityKind,
} from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { Applicability, RegisterVocabRef } from './types';

// The register's pills (design/system/pills-and-labels.md; REG-01, REG-02,
// REG-03). "Applies" and "we comply" are separate facts, so each has its own
// function and neither reads the other. Tone comes from the kind, never from
// a key or a label a bank may reword.

// Gap (slot order): gap status, severity, source.

export interface GapFacts {
  status: KindRef<GapKind>;
  severity: KindRef<SeverityKind>;
  source?: VocabularyRef;
}

export const GAP_SLOT_ORDER = { status: 10, severity: 20, source: 30 } as const;

export function presentGap(gap: GapFacts): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `gap-status:${gap.status.key}`, label: gap.status.label, tone: gapTone[gap.status.kind], order: GAP_SLOT_ORDER.status },
    { key: `severity:${gap.severity.key}`, label: gap.severity.label, tone: severityTone[gap.severity.kind], order: GAP_SLOT_ORDER.severity },
  ];
  if (gap.source !== undefined) {
    pills.push({ key: `source:${gap.source.key}`, label: gap.source.label, tone: slotTone.source, order: GAP_SLOT_ORDER.source });
  }
  return pills.sort(byOrder);
}

// Applicability is a fixed kind the API names in its own words; the tone map
// predates the contract and names the same three answers its own way.
const APPLICABILITY_KIND: Record<Applicability, ApplicabilityKind> = {
  applies: 'applies',
  not_applicable: 'does_not_apply',
  under_assessment: 'not_assessed',
};

const APPLICABILITY_LABEL: Record<Applicability, MessageKey> = {
  applies: 'obligationApplicability.applies',
  not_applicable: 'obligationApplicability.notApplicable',
  under_assessment: 'obligationApplicability.underAssessment',
};

export function presentApplicability(applicability: Applicability, t: Translate): PresentedPill {
  return {
    key: `applicability:${applicability}`,
    label: t(APPLICABILITY_LABEL[applicability]),
    tone: applicabilityTone[APPLICABILITY_KIND[applicability]],
    order: OBLIGATION_SLOT_ORDER.applicability,
  };
}

function isComplianceKind(kind: string | null): kind is ComplianceKind {
  return kind !== null && kind in complianceTone;
}

/** A row of the bank's `compliance_status` list: its own label, the tone of its fixed category. */
export function presentCompliance(status: RegisterVocabRef): PresentedPill {
  return {
    key: `compliance:${status.key}`,
    label: status.label,
    tone: complianceTone[isComplianceKind(status.kind) ? status.kind : 'not_assessed'],
    order: OBLIGATION_SLOT_ORDER.complianceStatus,
  };
}

function isRiskKind(kind: string | null): kind is RiskKind {
  return kind !== null && kind in riskTone;
}

export function presentRisk(risk: RegisterVocabRef): PresentedPill {
  return { key: `risk:${risk.key}`, label: risk.label, tone: riskTone[isRiskKind(risk.kind) ? risk.kind : 'low'], order: 0 };
}

export interface ComplianceHeaderFacts {
  applicability: Applicability;
  complianceStatus: RegisterVocabRef;
  entities: readonly { orgUnitName: string; applicability: Applicability; complianceStatus: RegisterVocabRef }[];
}

/**
 * The header's compliance slot: the server's worst-of status, and where the
 * obligation spans several legal entities it applies to, the one that sets
 * it named beside it. Nothing where it applies nowhere: no status is asked
 * while it does not apply.
 */
export function presentComplianceHeader(entry: ComplianceHeaderFacts, t: Translate): { pill: PresentedPill; weakest: string | null } | null {
  const applying = entry.entities.filter((entity) => entity.applicability === 'applies');
  if (entry.entities.length === 0 ? entry.applicability !== 'applies' : applying.length === 0) return null;
  const weakest = applying.length > 1 ? applying.find((entity) => entity.complianceStatus.kind === entry.complianceStatus.kind) : undefined;
  return {
    pill: presentCompliance(entry.complianceStatus),
    weakest: weakest === undefined ? null : t('obligationStatus.weakestEntity', { entity: weakest.orgUnitName }),
  };
}
