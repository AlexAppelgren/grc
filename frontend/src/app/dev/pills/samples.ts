import type { RoadmapItemFacts } from '@/features/home/roadmap-presentation';
import type { InstrumentFacts } from '@/features/library/instrument-presentation';
import type { ObligationFacts, ScopeFacts } from '@/features/library/obligation-presentation';
import type { GapFacts } from '@/features/register/register-presentation';
import type { KindRef } from '@/features/shared/presentation-types';
import type { ComplianceKind, GapKind, SeverityKind, UrgencyKind } from '@/features/shared/tone-by-kind';
import type { ChangeFacts, CaseStatusFacts } from '@/features/watch/change-presentation';
import type { RowFacts } from '@/components/inventory/ObligationRow';
import type { AccessEntry, AccessKey } from '@/features/agent-access/types';
import type { AgentDefinition, AgentRun, ResearchRequest, TenantAgent } from '@/features/agents/types';
import type { ScanState } from '@/features/cases/types';
import type { NotificationKind } from '@/features/collab/types';
import type { WorkItem } from '@/features/my-work/types';
import type { Participant } from '@/features/participants/types';
import type { PrivateProposalRow } from '@/features/private-records/types';
import type { Applicability } from '@/features/register/types';
import type { SupportAccessGrant } from '@/features/support-access/types';

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

// ---------------------------------------------------------------------------
// R2 (r2-gallery-coldstart-demo): the register, cases, collaboration, the bank's
// own agents and access, support grants and the bank's own records. Each sample
// holds only the facts its presentation function reads.
// ---------------------------------------------------------------------------

const compliant = complianceStatuses[0] as KindRef<ComplianceKind>;

/** Register entries as inventory rows: the library's slots, then the bank's applicability and status. */
export const registerEntries: readonly RowFacts[] = [
  {
    instrument: { key: 'lvm', shortName: 'LVM' },
    binding: true,
    bindingLevel: { key: 'act', kind: null, label: 'Act' },
    openChangeCount: 2,
    tags: [],
    tenantTags: [],
    privateToUs: false,
    applicability: 'applies',
    complianceStatus: partly,
  },
  {
    instrument: { key: 'esmagl', shortName: 'ESMAGL' },
    binding: false,
    bindingLevel: { key: 'eu_guidance', kind: null, label: 'EU guidance' },
    openChangeCount: 0,
    tags: [],
    tenantTags: [],
    privateToUs: false,
    applicability: 'not_applicable',
    complianceStatus: null,
  },
  {
    instrument: { key: 'own-outsourcing-policy', shortName: 'Outsourcing policy' },
    binding: true,
    bindingLevel: { key: 'internal', kind: null, label: 'Internal rule' },
    openChangeCount: 0,
    tags: [],
    tenantTags: [],
    privateToUs: true,
    applicability: 'applies',
    complianceStatus: compliant,
  },
];

export const applicabilities: readonly Applicability[] = ['applies', 'not_applicable', 'under_assessment'];

/** Every case category, and one carrying the bank's own sub-status, which changes the words and never the tone. */
export const caseStatuses: readonly CaseStatusFacts[] = [
  { category: 'new' },
  { category: 'assigned' },
  { category: 'assessing', subStatus: { key: 'waiting-for-legal', label: 'Waiting for legal' } },
  { category: 'implementing' },
  { category: 'signoff' },
  { category: 'closed' },
  { category: 'dismissed' },
];

export const scanStates: readonly ScanState[] = ['pending', 'clean', 'error', 'infected'];

/** An open action due before the gallery's day is overdue; a done one never is. */
export const actionsDue = {
  today: new Date('2026-09-15T12:00:00Z'),
  actions: [
    { dueDate: '2026-09-01', done: false },
    { dueDate: '2026-09-01', done: true },
  ],
} as const;

const JOHAN = { id: 'u-johan', name: 'Johan Berg' };
const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };

/** The reader's own row reads "You"; a colleague's reads nothing; a contributor team is the bank's own row. */
export const participants: { meId: string; rows: readonly Participant[]; team: Participant } = {
  meId: JOHAN.id,
  rows: [
    { id: 'p-1', person: JOHAN, team: null, addedBy: SARA, addedAt: '2026-09-01T09:00:00Z' },
    { id: 'p-2', person: SARA, team: null, addedBy: SARA, addedAt: '2026-09-01T09:00:00Z' },
  ],
  team: { id: 'p-3', person: null, team: { key: 'legal', kind: null, label: 'Legal' }, addedBy: SARA, addedAt: '2026-09-01T09:00:00Z' },
};

export const notificationKinds: readonly NotificationKind[] = [
  'mention',
  'assigned',
  'participant_added',
  'signoff_requested',
  'approval_requested',
  'due_soon',
  'review_due',
  'proposal_waiting',
  'overdue',
  'escalation',
  'involved_item_changed',
  'saved_search_hit',
];

/** My work repeats the record's own pills: an entry's compliance status, a case's urgency. */
export const workItems: readonly Pick<WorkItem, 'status' | 'urgency'>[] = [
  { status: { key: 'gap', kind: 'gap', label: 'Gap' }, urgency: null },
  { status: null, urgency: { key: 'act_now', kind: null, label: 'Act now' } },
];

/** A certificate's expiry and next audit are our own deadlines, never a regulator's. */
export const certificateDeadlines: readonly RoadmapItemFacts[] = [{ ourDeadline: true }, { ourDeadline: true }];

export const tenantAgents: readonly Pick<TenantAgent, 'enabled' | 'pausedAt'>[] = [
  { enabled: true, pausedAt: null },
  { enabled: true, pausedAt: '2026-09-14T08:00:00Z' },
  { enabled: false, pausedAt: null },
];

export const agentRuns: readonly Pick<AgentRun, 'status' | 'interruptedAt'>[] = [
  { status: 'succeeded', interruptedAt: null },
  { status: 'running', interruptedAt: null },
  { status: 'interrupted', interruptedAt: '2026-09-14T08:00:00Z' },
  { status: 'failed', interruptedAt: null },
];

export const researchRequests: readonly Pick<ResearchRequest, 'status'>[] = (['queued', 'running', 'done', 'failed', 'rejected', 'cancelled'] as const).map((status) => ({ status }));

export const definitions: readonly AgentDefinition[] = [
  { id: 'd-1', key: 'watch-sweeper', description: '', scope: 'platform', active: true, currentVersion: 3, publishedAt: '2026-09-01T09:00:00Z', tenantConfigurable: false },
  { id: 'd-2', key: 'bank-researcher', description: '', scope: 'tenant', active: false, currentVersion: 0, publishedAt: null, tenantConfigurable: true },
];

/** An entry reads the register only when the organisation's switch and its own toggle are both on. */
export const accessEntries: readonly { entry: Pick<AccessEntry, 'active' | 'tenantReach'>; orgReach: boolean }[] = [
  { entry: { active: true, tenantReach: true }, orgReach: true },
  { entry: { active: true, tenantReach: true }, orgReach: false },
  { entry: { active: false, tenantReach: false }, orgReach: true },
];

export const credentials: { now: Date; keys: readonly AccessKey[] } = {
  now: new Date('2026-09-15T12:00:00Z'),
  keys: [
    { id: 'k-1', kind: 'service', name: 'Order router', keyPrefix: 'cw_1', scopes: ['library:read', 'tenant:read'], person: null, createdAt: '2026-09-01T09:00:00Z', expiresAt: null, lastUsedAt: null, revokedAt: null },
    { id: 'k-2', kind: 'personal', name: 'My notebook', keyPrefix: 'cw_2', scopes: ['library:read'], person: JOHAN, createdAt: '2026-06-01T09:00:00Z', expiresAt: '2026-09-01T09:00:00Z', lastUsedAt: null, revokedAt: null },
    { id: 'k-3', kind: 'service', name: 'Old export', keyPrefix: 'cw_3', scopes: ['search:read'], person: null, createdAt: '2026-06-01T09:00:00Z', expiresAt: null, lastUsedAt: null, revokedAt: '2026-09-10T09:00:00Z' },
  ],
};

export const supportGrants: readonly Pick<SupportAccessGrant, 'state'>[] = (['pending', 'active', 'ended', 'revoked', 'declined', 'lapsed'] as const).map((state) => ({ state }));

/** The bank's own obligation, its header marked "Private to us". */
export const privateObligation: ObligationFacts = {
  instrument: { key: 'own-outsourcing-policy', label: 'Outsourcing policy' },
  regime: { key: 'banking', label: 'Banking' },
  binding: true,
  complianceStatus: compliant,
  privateToUs: true,
};

/** The bank's own queue: an agent's proposal wears "Proposed by our agent"; a person's names them as text. */
export const privateProposals: readonly Pick<PrivateProposalRow, 'kind' | 'status' | 'origin'>[] = [
  { kind: 'new_obligation', status: 'open', origin: 'agent' },
  { kind: 'new_instrument', status: 'approved', origin: 'person' },
];

export const scopeItemResearch: readonly string[] = ['waiting_for_agent', 'researching', 'researched'];
