import type { Me } from '@/features/identity/types';
import type { ChangeRow } from '@/features/watch/api';
import { presentChangeRow } from '@/features/watch/change-presentation';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n/messages';

// The lead card (design/screens/tenant-today.html, tenant-briefing.html;
// design/system/pills-and-labels.md "Computed" row): the `brand` pill "Lead"
// first, then the change's own pills in their fixed slot order. One
// presentation function, so Today's card and the briefing's card can never
// choose two different pill sets for the same change.
export function presentLead(row: ChangeRow, t: Translate): PresentedPill[] {
  const lead: PresentedPill = { key: 'lead', label: t('pill.lead'), tone: slotTone.lead, order: -1 };
  return [lead, ...presentChangeRow(row, 'row', t)];
}

// "Decide now" (HOM-01, D-23): one line per queue count on GET /me, in the
// card's order, each shown only to someone whose permission unlocks it and
// each with the way to where the decision is made. A count behind a
// permission the reader lacks is 0 on the server too; hiding its line keeps
// the panel to what this person can act on. Proposals have no line to follow:
// the bank's own proposals are decided in the console, not here.
type MeCounts = NonNullable<Me['counts']>;

export interface DecideNowLine {
  key: keyof MeCounts;
  message: MessageKey;
  count: number;
  href: string | null;
}

const DECIDE_NOW: readonly { key: keyof MeCounts; message: MessageKey; permission: string | null; href: string | null }[] = [
  { key: 'triage', message: 'today.decideNow.triage', permission: 'cases.triage', href: '/watch' },
  { key: 'signoffs', message: 'today.decideNow.signoffs', permission: 'cases.signoff', href: '/watch?tab=inProgress' },
  { key: 'riskAcceptances', message: 'today.decideNow.riskAcceptances', permission: 'risk.accept.approve', href: '/gaps' },
  { key: 'supportAccessRequests', message: 'today.decideNow.supportAccessRequests', permission: 'security.manage', href: '/admin/support-access' },
  { key: 'tenantReachRequests', message: 'today.decideNow.tenantReachRequests', permission: 'security.manage', href: '/admin/security' },
  { key: 'assignedToMe', message: 'today.decideNow.assignedToMe', permission: null, href: '/watch' },
  { key: 'proposals', message: 'today.decideNow.proposals', permission: 'proposals.create', href: null },
];

export function decideNowLines(counts: MeCounts, permissions: readonly string[]): DecideNowLine[] {
  return DECIDE_NOW.filter((line) => line.permission === null || permissions.includes(line.permission)).map(({ key, message, href }) => ({
    key,
    message,
    count: counts[key],
    href,
  }));
}
