import { describe, expect, it } from 'vitest';

import { groupSupportGrants, presentSupportGrant, supportSessionProblemCopy, supportStateTone } from '@/features/support-access/support-access-presentation';
import type { SupportAccessGrant, SupportAccessState } from '@/features/support-access/types';
import { createT } from '@/shared/i18n';

const t = createT('en');

const STATES: SupportAccessState[] = ['pending', 'active', 'ended', 'revoked', 'declined', 'lapsed', 'recovery'];

function grant(id: string, state: SupportAccessState): SupportAccessGrant {
  return { id, state, purpose: 'p', ticketRef: '', hours: 1, platformPerson: { id: 'p', name: 'P' }, requestedAt: '2026-09-25T07:00:00Z', decidedBy: null, decidedAt: null, endsAt: null };
}

describe('support access presentation', () => {
  it('takes its tone from the state kind: waiting is warning, live is notice, the rest are facts', () => {
    expect(supportStateTone).toEqual({ pending: 'warning', active: 'notice', ended: 'information', revoked: 'information', declined: 'information', lapsed: 'information', recovery: 'information' });
    expect(presentSupportGrant({ state: 'pending' }, t)).toEqual([{ key: 'state:pending', label: 'Waiting for approval', tone: 'warning', order: 0 }]);
    for (const state of STATES) expect(presentSupportGrant({ state }, t)[0]?.label).not.toMatch(/^supportAccess\./);
  });

  it('splits the list into waiting, live and history, keeping the order it came in', () => {
    const grants = STATES.map((state) => grant(state, state));
    const { pending, active, history } = groupSupportGrants(grants);
    expect(pending.map((g) => g.id)).toEqual(['pending']);
    expect(active.map((g) => g.id)).toEqual(['active']);
    expect(history.map((g) => g.id)).toEqual(['ended', 'revoked', 'declined', 'lapsed', 'recovery']);
  });

  it('words the two refusals a support session meets from their codes', () => {
    expect(supportSessionProblemCopy(t)).toEqual({
      support_read_only: 'A support session can only read. Nothing was changed.',
      support_access_ended: 'Support access has ended. Nothing more can be read.',
    });
  });
});
