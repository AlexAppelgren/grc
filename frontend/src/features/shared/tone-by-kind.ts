import type { PillTone } from '@/components/ui/pill-tones';

// Tone by kind and by slot (design/system/pills-and-labels.md, "Where tone
// comes from"). Kinds are the fixed enums behind a severity scale; the
// vocabulary rows an admin manages carry a kind and inherit its tone. A new
// compliance sub-status inherits the tone of its category.

export type UrgencyKind = 'act_now' | 'within_3_months' | 'six_plus_months' | 'monitor' | 'no_action';
export type ComplianceKind = 'compliant' | 'partly' | 'gap' | 'not_assessed';
export type GapKind = 'open' | 'remediating' | 'risk_accepted' | 'closed';
export type SeverityKind = 'high' | 'medium' | 'low';
export type ApplicabilityKind = 'applies' | 'does_not_apply' | 'not_assessed';

export const urgencyTone: Record<UrgencyKind, PillTone> = {
  act_now: 'negative',
  within_3_months: 'warning',
  six_plus_months: 'notice',
  monitor: 'information',
  no_action: 'positive',
};

export const complianceTone: Record<ComplianceKind, PillTone> = {
  compliant: 'positive',
  partly: 'warning',
  gap: 'negative',
  not_assessed: 'information',
};

export const gapTone: Record<GapKind, PillTone> = {
  open: 'negative',
  remediating: 'warning',
  risk_accepted: 'information',
  closed: 'positive',
};

export const severityTone: Record<SeverityKind, PillTone> = {
  high: 'negative',
  medium: 'warning',
  low: 'information',
};

// "Applies" is positive on the system card's obligation row; the other two
// are neutral facts.
export const applicabilityTone: Record<ApplicabilityKind, PillTone> = {
  applies: 'positive',
  does_not_apply: 'information',
  not_assessed: 'information',
};

// Slot tones: fixed by where the pill sits.
export const slotTone = {
  changeType: 'notice',
  instrument: 'brand',
  flag: 'brand',
  libraryTag: 'brand',
  scopeTerm: 'brand',
  regime: 'information',
  workflowStatus: 'information',
  bindingLevel: 'information',
  guidance: 'information',
  tenantTag: 'information',
  source: 'information',
  waitingForApproval: 'warning',
  changePending: 'warning',
  openChanges: 'notice',
  you: 'positive',
  ourDeadline: 'brand',
  lead: 'brand',
} as const satisfies Record<string, PillTone>;
