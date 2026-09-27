import type { PillTone } from '@/components/ui/pill-tones';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { SupportAccessGrant, SupportAccessState } from '@/features/support-access/types';
import type { MessageKey, Translate } from '@/shared/i18n';

// A support access grant's state is a fixed kind (design/system/pills-and-labels.md):
// waiting for approval is warning, as everywhere it appears; active is notice,
// like a running agent; every closed state is a plain fact.
export const supportStateTone: Record<SupportAccessState, PillTone> = {
  pending: 'warning',
  active: 'notice',
  ended: 'information',
  revoked: 'information',
  declined: 'information',
  lapsed: 'information',
  recovery: 'information',
};

const stateLabel: Record<SupportAccessState, MessageKey> = {
  pending: 'supportAccess.state.pending',
  active: 'supportAccess.state.active',
  ended: 'supportAccess.state.ended',
  revoked: 'supportAccess.state.revoked',
  declined: 'supportAccess.state.declined',
  lapsed: 'supportAccess.state.lapsed',
  recovery: 'supportAccess.state.recovery',
};

export function presentSupportGrant(grant: Pick<SupportAccessGrant, 'state'>, t: Translate): PresentedPill[] {
  return [{ key: `state:${grant.state}`, label: t(stateLabel[grant.state]), tone: supportStateTone[grant.state], order: 0 }];
}

/** The panel's three sections: waiting for a decision, access now, and everything else. */
export function groupSupportGrants(grants: readonly SupportAccessGrant[]): { pending: SupportAccessGrant[]; active: SupportAccessGrant[]; history: SupportAccessGrant[] } {
  return {
    pending: grants.filter((g) => g.state === 'pending'),
    active: grants.filter((g) => g.state === 'active'),
    history: grants.filter((g) => g.state !== 'pending' && g.state !== 'active'),
  };
}

/**
 * The two refusals a support session meets, by code (playbook 4.4): pass to
 * `ProblemAlert`'s `codes` wherever an action or a page may meet them.
 */
export function supportSessionProblemCopy(t: Translate): Readonly<Record<string, string>> {
  return {
    support_read_only: t('supportAccess.problem.readOnly'),
    support_access_ended: t('supportAccess.problem.ended'),
  };
}
