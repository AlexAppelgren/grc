import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { CaseWorkflow } from '@/features/cases/types';
import type { ChangeDetail } from '@/features/watch/api';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { TriagePanel } from './TriagePanel';

// Triage, the next step, the one-person close and Move back to triage on the
// change page (design/screens/tenant-change.html, case panels part A and
// the closed and dismissed states of part B; CAS-02, CAS-08, D-92). Every
// control shows only when the case's allowedTransitions and the reader's
// permissions both allow it, so a reader never sends a request that could
// answer 403; every refusal renders where it was made, from the server's
// answer.

const CHANGE = { id: 'c-1', model: 'Research agent 0.4' } as unknown as ChangeDetail;
const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };
const JOHAN = { id: 'u-johan', name: 'Johan Berg' };

function workflowOf(overrides: Partial<CaseWorkflow> = {}): CaseWorkflow {
  return {
    id: 'case-1',
    category: 'new',
    allowedTransitions: ['assigned', 'dismissed'],
    urgency: { key: 'act_now', kind: 'negative', label: 'Act now' },
    urgencyConfirmed: false,
    owner: null,
    ownerId: null,
    ownerTeam: null,
    triagedBy: null,
    triagedAt: null,
    dismissedReason: null,
    dismissedBy: null,
    dismissedAt: null,
    closeReason: null,
    closedAt: null,
    closedNote: null,
    assessment: null,
    subStatus: null,
    version: 3,
    ...overrides,
  } as CaseWorkflow;
}

const LISTS: Record<string, unknown[]> = {
  urgency: [
    { key: 'act_now', kind: 'negative', label: 'Act now', usageNote: '' },
    { key: 'within_3_months', kind: 'warning', label: 'Within 3 months', usageNote: '' },
  ],
  dismissal_reason: [
    { key: 'out_of_scope', kind: null, label: 'Out of scope', usageNote: 'The change does not touch anything we do.' },
    { key: 'duplicate', kind: null, label: 'Duplicate', usageNote: 'Already handled in another case.' },
  ],
  team: [
    { key: 'cards', kind: null, label: 'Cards compliance', usageNote: '' },
    { key: 'old_desk', kind: null, label: 'Old desk', usageNote: '', active: false },
  ],
  close_reason: [
    { key: 'no_action', kind: 'no_action', label: 'No action needed', usageNote: 'Applies, but nothing has to change.' },
    { key: 'not_applicable', kind: 'not_applicable', label: 'Not applicable', usageNote: '' },
    { key: 'signed_off', kind: 'signed_off', label: 'Signed off', usageNote: '' },
  ],
};

/** Reads answer the lists and the owner list; every write answers `write`. What is returned is every request. */
function serve(write: Answer = { status: 200, data: {} }): Sent[] {
  return installAdapter((sent) => {
    if (sent.method !== 'get') return write;
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: [SARA, JOHAN] };
    const list = sent.path.replace('/api/v1/vocab/', '');
    if (list in LISTS) return { status: 200, data: { items: LISTS[list], total: LISTS[list]!.length } };
    return { status: 200, data: { user: { locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [] } };
  });
}

const writes = (sent: Sent[]) => sent.filter((request) => request.method !== 'get');
/** What the panel itself asked for: the signed-in session every screen reads for its dates is not the panel's. */
const panelRequests = (sent: Sent[]) => sent.filter((request) => request.path.startsWith('/api/v1/vocab') || request.path.startsWith('/api/v1/reference') || request.method !== 'get');

function renderPanel(workflow: CaseWorkflow, permissions: string[]): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <TriagePanel change={CHANGE} workflow={workflow} />
        </PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

describe('triage, needs triage', () => {
  it('offers the owners who can work cases and the suggested urgency, and confirms with both', async () => {
    const sent = serve();
    renderPanel(workflowOf(), ['cases.triage']);

    const owner = screen.getByRole('combobox', { name: 'Owner' });
    await within(owner).findByRole('option', { name: 'Johan Berg' });
    expect(sent.find((request) => request.path === '/api/v1/reference/people')?.params).toEqual({ permission: 'cases.work' });
    const urgency = screen.getByRole('combobox', { name: 'Urgency' });
    await within(urgency).findByRole('option', { name: 'Within 3 months' });
    expect(urgency).toHaveValue('act_now');
    expect(screen.getByText('Suggested by Research agent 0.4')).toBeInTheDocument();

    fireEvent.change(urgency, { target: { value: 'within_3_months' } });
    fireEvent.change(owner, { target: { value: 'u-johan' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and assign' }));

    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    const [post] = writes(sent);
    expect([post?.method, post?.path, post?.body]).toEqual(['post', '/api/v1/changes/c-1/triage', { urgency: 'within_3_months', ownerId: 'u-johan' }]);
  });

  it('offers the bank’s active teams beside the owner and sends the team’s key', async () => {
    const sent = serve();
    renderPanel(workflowOf(), ['cases.triage']);

    const team = screen.getByRole('combobox', { name: 'Owner team (optional)' });
    await within(team).findByRole('option', { name: 'Cards compliance' });
    expect(within(team).queryByRole('option', { name: 'Old desk' })).toBeNull();
    expect(team).toHaveValue('');
    fireEvent.change(screen.getByRole('combobox', { name: 'Owner' }), { target: { value: 'u-sara' } });
    fireEvent.change(team, { target: { value: 'cards' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and assign' }));

    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect(writes(sent)[0]?.body).toEqual({ urgency: 'act_now', ownerId: 'u-sara', ownerTeam: 'cards' });
  });

  it('renders a 422 against the team field it names', async () => {
    serve({ status: 422, data: { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.ownerTeam', message: 'Too long' }] } });
    renderPanel(workflowOf(), ['cases.triage']);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and assign' }));
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Owner team (optional)' })).toHaveAttribute('aria-invalid', 'true'));
    expect(screen.queryByText('Some fields need attention.')).toBeNull();
  });

  it('renders a 422 against the owner field it names', async () => {
    serve({ status: 422, data: { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.ownerId', message: 'Field required' }] } });
    renderPanel(workflowOf(), ['cases.triage']);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and assign' }));

    expect(await screen.findByText('Choose who owns this case.')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Owner' })).toHaveAttribute('aria-invalid', 'true');
  });

  it('a 422 naming a field the form does not show is said in the server’s words', async () => {
    serve({ status: 422, data: { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.ownerId' }, { field: 'body.subStatus' }] } });
    renderPanel(workflowOf(), ['cases.triage']);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and assign' }));
    expect(await screen.findByText('Choose who owns this case.')).toBeInTheDocument();
    expect(screen.getByText('Some fields need attention.')).toBeInTheDocument();
  });

  it('a stale write offers a reload and keeps the choice made', async () => {
    serve({ status: 409, data: { code: 'stale_write', detail: 'Someone else saved first.', currentVersion: 4 } });
    renderPanel(workflowOf(), ['cases.triage']);
    const owner = screen.getByRole('combobox', { name: 'Owner' });
    await within(owner).findByRole('option', { name: 'Sara Lindqvist' });
    fireEvent.change(owner, { target: { value: 'u-sara' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and assign' }));

    expect(await screen.findByRole('button', { name: 'Reload their version' })).toBeInTheDocument();
    expect(screen.getByText(/Nothing of yours was saved or merged/)).toBeInTheDocument();
    expect(owner).toHaveValue('u-sara');
  });

  it('dismisses with a reason from the bank’s own list, and the refusal names the reason', async () => {
    const sent = serve({ status: 422, data: { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.reasonKey', message: 'too short' }] } });
    renderPanel(workflowOf(), ['cases.triage']);
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    const dialog = await screen.findByRole('dialog', { name: 'Dismiss this change?' });
    expect(await within(dialog).findByRole('radio', { name: /Out of scope/ })).toBeInTheDocument();
    expect(within(dialog).getByText('The change does not touch anything we do.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Dismiss' }));
    expect(await within(dialog).findByText('Choose a reason for dismissing it.')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('radio', { name: /Duplicate/ }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(writes(sent)).toHaveLength(2));
    expect([writes(sent)[1]?.path, writes(sent)[1]?.body]).toEqual(['/api/v1/changes/c-1/dismiss', { reasonKey: 'duplicate' }]);
  });

  it('offers only the moves the case allows', () => {
    serve();
    renderPanel(workflowOf({ allowedTransitions: ['dismissed'] }), ['cases.triage']);
    expect(screen.queryByRole('button', { name: 'Confirm and assign' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dismiss' })).toBeInTheDocument();
  });

  it('without cases.triage: the facts, no control and no request at all', () => {
    const sent = serve();
    renderPanel(workflowOf(), ['cases.read', 'cases.work']);
    expect(screen.getByText('This change needs triage: an urgency and an owner. Someone who can triage changes will pick it up.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(panelRequests(sent)).toHaveLength(0);
  });
});

describe('the next step, assigned and assessing', () => {
  const assigned = workflowOf({
    category: 'assigned',
    allowedTransitions: ['assessing', 'closed'],
    owner: SARA,
    triagedBy: JOHAN,
    triagedAt: '2026-09-18T08:00:00Z',
    urgencyConfirmed: true,
  });

  it('says who owns it and who assigned it, and starts the assessment', async () => {
    const sent = serve();
    renderPanel(assigned, ['cases.work']);
    expect(screen.getByRole('heading', { name: 'Next step' })).toBeInTheDocument();
    expect(screen.getByText('Assigned to Sara Lindqvist by Johan Berg on 18 Sept 2026.')).toBeInTheDocument();
    expect(screen.queryByText(/Owner team/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Start assessment' }));
    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect([writes(sent)[0]?.method, writes(sent)[0]?.path]).toEqual(['post', '/api/v1/changes/c-1/assessment/start']);
  });

  it('names the owner team beside the owner, and nothing when there is none', () => {
    serve();
    renderPanel({ ...assigned, ownerTeam: { key: 'cards', kind: null, label: 'Cards compliance' } }, ['cases.work']);
    expect(screen.getByText('Owner team: Cards compliance.')).toBeInTheDocument();
  });

  it('No action closes on one person’s word with a reason of the no-action kind and an optional note', async () => {
    const sent = serve();
    renderPanel(assigned, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'No action' }));

    const dialog = await screen.findByRole('dialog', { name: 'Close without action?' });
    const reason = await within(dialog).findByRole('radio', { name: /No action needed/ });
    expect(within(dialog).queryByRole('radio', { name: /Signed off/ })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('radio', { name: /Not applicable/ })).not.toBeInTheDocument();
    fireEvent.click(reason);
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Note (optional)' }), { target: { value: 'Paid from client charges.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close the case' }));

    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect([writes(sent)[0]?.path, writes(sent)[0]?.body]).toEqual(['/api/v1/changes/c-1/close', { reasonKey: 'no_action', note: 'Paid from client charges.' }]);
  });

  it('while assessing offers No action and nothing to start', () => {
    serve();
    renderPanel(workflowOf({ ...assigned, category: 'assessing', allowedTransitions: ['implementing', 'closed'] }), ['cases.work']);
    expect(screen.getByRole('button', { name: 'No action' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start assessment' })).not.toBeInTheDocument();
  });

  it('without cases.work: who owns it, and no control', () => {
    const sent = serve();
    renderPanel(assigned, ['cases.read', 'cases.triage']);
    expect(screen.getByText('Assigned to Sara Lindqvist on 18 Sept 2026.')).toBeInTheDocument();
    expect(screen.getByText('The owner starts the impact assessment.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(panelRequests(sent)).toHaveLength(0);
  });
});

describe('dismissed and closed by one person', () => {
  const dismissed = workflowOf({
    category: 'dismissed',
    allowedTransitions: ['new'],
    dismissedReason: { key: 'out_of_scope', kind: null, label: 'Out of scope' },
    dismissedBy: SARA,
    dismissedAt: '2026-09-17T10:00:00Z',
  });

  it('a dismissed case names the reason and who, and moves back to triage', async () => {
    const sent = serve();
    renderPanel(dismissed, ['cases.triage']);
    expect(screen.getByRole('heading', { name: 'Dismissed' })).toBeInTheDocument();
    expect(screen.getByText('Out of scope')).toBeInTheDocument();
    expect(screen.getByText('Sara Lindqvist, 17 Sept 2026')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Move back to triage' }));
    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect([writes(sent)[0]?.path, writes(sent)[0]?.body]).toEqual(['/api/v1/changes/c-1/restore', null]);
  });

  it('without cases.triage, or when the case allows no way back, there is no Move back to triage', () => {
    serve();
    renderPanel(dismissed, ['cases.read']);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('a case closed without action names the reason and the note', () => {
    serve();
    renderPanel(
      workflowOf({
        category: 'closed',
        allowedTransitions: ['new'],
        closeReason: { key: 'no_action', kind: 'no_action', label: 'No action needed' },
        closedAt: '2026-09-18T10:00:00Z',
        closedNote: 'Our research is paid from client charges already reported.',
      }),
      ['cases.triage'],
    );
    expect(screen.getByRole('heading', { name: 'Closed' })).toBeInTheDocument();
    expect(screen.getByText('No action needed')).toBeInTheDocument();
    expect(screen.getByText('Our research is paid from client charges already reported.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move back to triage' })).toBeInTheDocument();
  });

  it('a case closed as not applicable shows why, from its assessment', () => {
    serve();
    renderPanel(
      workflowOf({
        category: 'closed',
        allowedTransitions: [],
        closeReason: { key: 'not_applicable', kind: 'not_applicable', label: 'Does not apply to us' },
        closedAt: '2026-09-18T10:00:00Z',
        assessment: { applies: 'no', why: 'We buy no third-party research.', whatMustChange: null, internalDeadline: null, effort: null, saved: true, savedAt: '2026-09-18T10:00:00Z', savedBy: JOHAN, version: 2 },
      }),
      ['cases.triage'],
    );
    expect(screen.getByText('Does not apply to us')).toBeInTheDocument();
    expect(screen.getByText('We buy no third-party research.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move back to triage' })).not.toBeInTheDocument();
  });

  it('a refused move back says why in place', async () => {
    serve({ status: 409, data: { code: 'invalid_transition', detail: 'This case cannot move there from where it is.' } });
    renderPanel(dismissed, ['cases.triage']);
    fireEvent.click(screen.getByRole('button', { name: 'Move back to triage' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This case cannot move there from where it is.');
  });
});
