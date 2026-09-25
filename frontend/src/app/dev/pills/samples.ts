import type { RoadmapItemFacts } from '@/features/home/roadmap-presentation';
import type { InstrumentFacts } from '@/features/library/instrument-presentation';
import type { ObligationFacts, ScopeFacts } from '@/features/library/obligation-presentation';
import type { GapFacts } from '@/features/register/register-presentation';
import type { KindRef } from '@/features/shared/presentation-types';
import type { ComplianceKind, GapKind, SeverityKind, UrgencyKind } from '@/features/shared/tone-by-kind';
import type { ChangeFacts } from '@/features/watch/change-presentation';

// Sample facts for the gallery, taken from design/system/pills-and-labels.html
// and the prototype's sample data. Labels here stand in for vocabulary rows;
// in the app they arrive from the API in the user's language.

export const urgencies: readonly KindRef<UrgencyKind>[] = [
  { key: 'act-now', kind: 'act_now', label: 'Act now' },
  { key: 'within-3-months', kind: 'within_3_months', label: 'Within 3 months' },
  { key: '6-plus-months', kind: 'six_months_plus', label: '6+ months' },
  { key: 'monitor', kind: 'monitor', label: 'Monitor' },
  { key: 'no-action', kind: 'no_action', label: 'No action' },
];

export const complianceStatuses: readonly KindRef<ComplianceKind>[] = [
  { key: 'compliant', kind: 'compliant', label: 'Compliant' },
  { key: 'partly', kind: 'partly', label: 'Partly compliant' },
  { key: 'gap', kind: 'gap', label: 'Gap' },
  { key: 'not-assessed', kind: 'not_assessed', label: 'Not assessed' },
];

export const gapStatuses: readonly KindRef<GapKind>[] = [
  { key: 'open', kind: 'open', label: 'Open' },
  { key: 'remediating', kind: 'remediating', label: 'Remediating' },
  { key: 'risk-accepted', kind: 'risk_accepted', label: 'Risk accepted' },
  { key: 'closed', kind: 'closed', label: 'Closed' },
];

export const severities: readonly KindRef<SeverityKind>[] = [
  { key: 'high', kind: 'high', label: 'High' },
  { key: 'medium', kind: 'medium', label: 'Medium' },
  { key: 'low', kind: 'low', label: 'Low' },
];

const actNow = urgencies[0] as KindRef<UrgencyKind>;
const within3 = urgencies[1] as KindRef<UrgencyKind>;
const partly = complianceStatuses[1] as KindRef<ComplianceKind>;
const gap = complianceStatuses[2] as KindRef<ComplianceKind>;

export interface ChangeSample {
  facts: ChangeFacts;
  authority: string;
  title: string;
}

export const changes: readonly ChangeSample[] = [
  {
    facts: {
      type: { key: 'adopted-rule', label: 'Adopted rule' },
      urgency: actNow,
      flags: [{ key: 'advice-perimeter', label: 'Advice perimeter' }],
      workflowStatus: { key: 'new', label: 'Needs triage' },
    },
    authority: 'Finansinspektionen, 12 Sep 2026',
    title: 'FI adopts amended rules on paying for investment research',
  },
  {
    facts: {
      type: { key: 'eu-proposal', label: 'EU proposal' },
      urgency: within3,
      flags: [{ key: 'ai', label: 'AI' }],
      tenantTags: [{ key: 'q4-review', label: 'Q4 review' }],
    },
    authority: 'EU Council and Parliament',
    title: 'Retail investment strategy: final compromise text',
  },
];

export interface ObligationSample {
  facts: ObligationFacts;
  title: string;
  meta: readonly string[];
}

export const obligations: readonly ObligationSample[] = [
  {
    facts: {
      instrument: { key: 'lvm', label: 'LVM' },
      regime: { key: 'securities', label: 'Securities' },
      binding: true,
      applicability: { key: 'applies', kind: 'applies', label: 'Applies' },
      complianceStatus: partly,
      openChangeCount: 2,
    },
    title: 'Assess appropriateness before non-advised trades in complex instruments',
    meta: ['9 kap.', 'Non-advised, Execution only'],
  },
  {
    facts: {
      instrument: { key: 'esmagl', label: 'ESMAGL' },
      regime: { key: 'securities', label: 'Securities' },
      binding: false,
      applicability: { key: 'applies', kind: 'applies', label: 'Applies' },
      complianceStatus: gap,
      libraryTags: [{ key: 'appropriateness', label: 'Appropriateness' }],
      tenantTags: [{ key: 'digital-investing', label: 'Digital investing' }],
    },
    title: 'Make appropriateness warnings prominent',
    meta: [],
  },
];

export const instruments: readonly InstrumentFacts[] = [
  {
    instrument: { key: 'fffs-2017-2', label: 'FFFS 2017:2' },
    level: { key: 'authority_regulation', label: 'FI regulation' },
    binding: true,
    jurisdiction: { key: 'SE', label: 'Sweden' },
    regime: { key: 'securities', label: 'Securities' },
  },
  {
    instrument: { key: 'esma-gl-appropriateness', label: 'ESMA guidelines' },
    level: { key: 'eu_guidance', label: 'EU guidance, level 3' },
    binding: false,
    jurisdiction: { key: 'EU', label: 'EU' },
  },
];

export const scopes: readonly ScopeFacts[] = [
  {
    dimension: 'legal_entity',
    terms: [
      { key: 'bank', label: 'Bank' },
      { key: 'fund-company', label: 'Fund company' },
    ],
    allSelected: false,
  },
  { dimension: 'service_type', terms: [{ key: 'advice', label: 'Advice' }], allSelected: true },
  { dimension: 'client_category', terms: [], allSelected: false },
];

export const gaps: readonly GapFacts[] = [
  { status: gapStatuses[0] as KindRef<GapKind>, severity: severities[0] as KindRef<SeverityKind>, source: { key: 'assessment', label: 'Impact assessment' } },
  { status: gapStatuses[1] as KindRef<GapKind>, severity: severities[1] as KindRef<SeverityKind>, source: { key: 'review', label: 'Annual review' } },
];

export const roadmapItems: readonly RoadmapItemFacts[] = [{ urgency: actNow, ourDeadline: false }, { ourDeadline: true }];
