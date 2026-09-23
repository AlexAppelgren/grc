import type { PillTone } from '@/components/ui/pill-tones';

// Tone by kind and by slot (design/system/pills-and-labels.md, "Where tone
// comes from"). Kinds are the fixed enums behind a severity scale; the
// vocabulary rows an admin manages carry a kind and inherit its tone. A new
// compliance sub-status inherits the tone of its category.

export type UrgencyKind = 'act_now' | 'within_3_months' | 'six_months_plus' | 'monitor' | 'no_action';
export type ComplianceKind = 'compliant' | 'partly' | 'gap' | 'not_assessed';
export type GapKind = 'open' | 'remediating' | 'risk_accepted' | 'closed';
export type SeverityKind = 'high' | 'medium' | 'low';
export type ApplicabilityKind = 'applies' | 'does_not_apply' | 'not_assessed';

export const urgencyTone: Record<UrgencyKind, PillTone> = {
  act_now: 'negative',
  within_3_months: 'warning',
  six_months_plus: 'notice',
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

// PRO-01, PRO-02: a proposal's status, on the queue's tabs and rows. `open`
// needs attention (warning, "Waiting"), `approved` is good (positive), and
// `rejected` and `superseded` are neutral facts the record still carries
// (information) — never negative, because a rejection is a decision made on
// purpose, not a failure.
export type ProposalStatusKind = 'open' | 'approved' | 'rejected' | 'superseded';

export const proposalStatusTone: Record<ProposalStatusKind, PillTone> = {
  open: 'warning',
  approved: 'positive',
  rejected: 'information',
  superseded: 'information',
};

// WAT-01: how a source check ended, as `CheckStatus` names it in the API.
// The coverage log and the feed's Coverage tab read the check, never the
// sentence it carries. `never` is the third member the coverage read answers:
// a source nobody has checked yet is a neutral fact, not a failure.
export type CheckStatusKind = 'ok' | 'failed' | 'never';

export const checkStatusTone: Record<CheckStatusKind, PillTone> = {
  ok: 'positive',
  failed: 'negative',
  never: 'information',
};

// ID-10: an agent key's state, computed from the key's own dates. Revoked
// and expired are the same warning: the key has stopped working and the row
// stays so the security log has something to point at.
export type ApiKeyStateKind = 'active' | 'never_used' | 'revoked' | 'expired';

export const apiKeyStateTone: Record<ApiKeyStateKind, PillTone> = {
  active: 'positive',
  never_used: 'information',
  revoked: 'warning',
  expired: 'warning',
};

// AUD-02: an AI log row's review state and a reader's verdict on an Ask
// answer, as the API names them. A draft nobody has reviewed is a neutral
// fact, as an agent's suggestion is; a person standing behind the words, as
// drafted or rewritten, is positive; a rejection is a decision made on
// purpose, so it stays neutral. A reader saying "wrong" needs a look, it is
// not itself bad. The purpose sits in `slotTone.aiPurpose`.
export type AiReviewKind = 'draft' | 'confirmed' | 'edited' | 'rejected';

export const aiReviewTone: Record<AiReviewKind, PillTone> = {
  draft: 'information',
  confirmed: 'positive',
  edited: 'positive',
  rejected: 'information',
};

export type AiFeedbackKind = 'helpful' | 'wrong';

export const aiFeedbackTone: Record<AiFeedbackKind, PillTone> = {
  helpful: 'positive',
  wrong: 'warning',
};

// "Applies" is positive on the system card's obligation row; the other two
// are neutral facts.
export const applicabilityTone: Record<ApplicabilityKind, PillTone> = {
  applies: 'positive',
  does_not_apply: 'information',
  not_assessed: 'information',
};

// Slot tones: fixed by where the pill sits. A header's "Guidance, comply or
// explain" needs attention (warning); a row's short "Guidance" stays a
// neutral fact (information), as the obligation and instrument cards show.
export const slotTone = {
  changeType: 'notice',
  // The queue's kind pill (console-queue.html): "New version", "Vocabulary"
  // and so on, in the same slot a change type occupies elsewhere.
  proposalKind: 'notice',
  instrument: 'brand',
  jurisdiction: 'brand',
  flag: 'brand',
  libraryTag: 'brand',
  scopeTerm: 'brand',
  regime: 'information',
  workflowStatus: 'information',
  instrumentLevel: 'information',
  bindingLevel: 'information',
  guidanceComplyOrExplain: 'warning',
  guidance: 'information',
  // SRC-02: how a search hit was won, keyword, concept or both — a neutral
  // fact about the query, never a person's choice (design/system/pills-and-labels.md).
  matchKind: 'information',
  tenantTag: 'information',
  source: 'information',
  waitingForApproval: 'warning',
  changePending: 'warning',
  openChanges: 'notice',
  you: 'positive',
  ourDeadline: 'brand',
  lead: 'brand',
  // Chunk 5, from the watch and console cards. A fact an agent put forward
  // is a neutral fact until a person settles it, which is why "Suggested by
  // the agent" and a match confidence read information and a confirmation
  // reads positive; a change still carrying unconfirmed facts needs a
  // library editor, so its count reads warning. A paused source is a fact
  // about the source, not a failure.
  suggested: 'information',
  confirmed: 'positive',
  factsToConfirm: 'warning',
  duplicate: 'information',
  agentVersion: 'brand',
  apiScope: 'information',
  sourceKind: 'information',
  paused: 'information',
  // A source that has gone past its cadence, or failed more times in a row
  // than the stale rule allows: it needs attention, it is not itself bad.
  stale: 'warning',
  // AUD-02: what a model call was for, a kind of call, as a change type is a kind of change.
  aiPurpose: 'notice',
} as const satisfies Record<string, PillTone>;
