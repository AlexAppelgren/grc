import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { CaseAssessment, CaseWorkflow } from '@/features/cases/types';
import type { ChangeDetail } from '@/features/watch/api';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { AssessmentPanel } from './AssessmentPanel';

// The impact assessment on the change page (design/screens/tenant-change.html,
// case panels part A; CAS-03, CAS-08, D-92). Editable with cases.contribute
// while the case is assessed or implemented, read-only for everyone else and
// for everyone from waiting for sign-off on. "No" closes the case, so only a
// holder of cases.work is offered it, and it asks first. A save somebody
// else's overtook keeps the person's text and offers a reload, never a merge.

const CHANGE = { id: 'c-1' } as unknown as ChangeDetail;
const JOHAN = { id: 'u-johan', name: 'Johan Berg' };

const SAVED: CaseAssessment = {
  applies: 'yes',
  why: 'We pay two research providers from our own account.',
  whatMustChange: 'Written criteria for the annual quality assessment.',
  internalDeadline: '2026-09-30',
  effort: { key: 'm', kind: null, label: 'M, weeks of work' },
  saved: true,
  savedAt: '2026-09-19T07:12:00Z',
  savedBy: JOHAN,
  version: 2,
};

function workflowOf(overrides: Partial<CaseWorkflow> = {}): CaseWorkflow {
  return {
    id: 'case-1',
    category: 'assessing',
    allowedTransitions: ['implementing', 'closed'],
    subStatus: { key: 'waiting_for_legal', kind: 'assessing', label: 'Waiting for legal' },
    assessment: SAVED,
    closeReason: null,
    closedNote: null,
    version: 5,
    ...overrides,
  } as CaseWorkflow;
}

const LISTS: Record<string, unknown[]> = {
  effort_size: [
    { key: 's', kind: null, label: 'S, days of work', usageNote: '' },
    { key: 'm', kind: null, label: 'M, weeks of work', usageNote: '' },
  ],
  case_sub_status: [
    { key: 'assessing', kind: 'assessing', label: 'Assessing', usageNote: '' },
    { key: 'waiting_for_legal', kind: 'assessing', label: 'Waiting for legal', usageNote: '' },
    { key: 'in_progress', kind: 'implementing', label: 'In progress', usageNote: '' },
  ],
};

function serve(write: Answer = { status: 200, data: { assessment: { ...SAVED, version: 3 } } }): Sent[] {
  return installAdapter((sent) => {
    if (sent.method !== 'get') return write;
    const list = sent.path.replace('/api/v1/vocab/', '');
    if (list in LISTS) return { status: 200, data: { items: LISTS[list], total: LISTS[list]!.length } };
    return { status: 200, data: { user: { locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [] } };
  });
}

const writes = (sent: Sent[]) => sent.filter((request) => request.method !== 'get');
const panelRequests = (sent: Sent[]) => sent.filter((request) => request.path.startsWith('/api/v1/vocab') || request.method !== 'get');

function renderPanel(workflow: CaseWorkflow, permissions: string[]): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <AssessmentPanel change={CHANGE} workflow={workflow} />
        </PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

const WORKER = ['cases.read', 'cases.contribute', 'cases.work'];
const CONTRIBUTOR = ['cases.read', 'cases.contribute'];

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

describe('the assessment form', () => {
  it('starts from what was saved and says which version and who saved it', async () => {
    serve();
    renderPanel(workflowOf(), WORKER);
    expect(screen.getByText('Version 2')).toBeInTheDocument();
    expect(screen.getByText(/^Saved by Johan Berg, 19 Sept 2026/)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Yes' })).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Why' })).toHaveValue('We pay two research providers from our own account.');
    expect(screen.getByRole('textbox', { name: 'What must change' })).toHaveValue('Written criteria for the annual quality assessment.');
    expect(screen.getByLabelText('Internal deadline')).toHaveValue('2026-09-30');
    await within(screen.getByRole('combobox', { name: 'Effort' })).findByRole('option', { name: 'M, weeks of work' });
    expect(screen.getByRole('combobox', { name: 'Effort' })).toHaveValue('m');
  });

  it('offers the statuses of the case’s own category only', async () => {
    serve();
    renderPanel(workflowOf(), WORKER);
    const status = screen.getByRole('combobox', { name: 'Status' });
    await within(status).findByRole('option', { name: 'Waiting for legal' });
    expect(within(status).queryByRole('option', { name: 'In progress' })).not.toBeInTheDocument();
    expect(status).toHaveValue('waiting_for_legal');
  });

  it('saves the whole assessment as keys and dates, with what the person typed', async () => {
    const sent = serve();
    renderPanel(workflowOf(), WORKER);
    await within(screen.getByRole('combobox', { name: 'Effort' })).findByRole('option', { name: 'S, days of work' });
    fireEvent.click(screen.getByRole('radio', { name: 'Partly' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Why' }), { target: { value: '  Only the discretionary portfolios.  ' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Effort' }), { target: { value: 's' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save assessment' }));

    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    const [put] = writes(sent);
    expect([put?.method, put?.path]).toEqual(['put', '/api/v1/changes/c-1/assessment']);
    expect(put?.body).toEqual({
      applies: 'partly',
      why: 'Only the discretionary portfolios.',
      whatMustChange: 'Written criteria for the annual quality assessment.',
      internalDeadline: '2026-09-30',
      effort: 's',
      subStatus: 'waiting_for_legal',
    });
    expect(await screen.findByText('Assessment saved. It is now version 3.')).toBeInTheDocument();
  });

  it('renders a 422 against the field it names', async () => {
    serve({ status: 422, data: { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.why', message: 'too short' }] } });
    renderPanel(workflowOf(), WORKER);
    fireEvent.change(screen.getByRole('textbox', { name: 'Why' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save assessment' }));
    expect(await screen.findByText('Say why it applies, or why it does not.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Why' })).toHaveAttribute('aria-invalid', 'true');
  });

  it('an unknown key is refused in the server’s own words', async () => {
    serve({ status: 422, data: { code: 'unknown_key', detail: 'Not a case_sub_status key of assessing: waiting_for_board.', validKeys: ['assessing'] } });
    renderPanel(workflowOf(), WORKER);
    fireEvent.click(screen.getByRole('button', { name: 'Save assessment' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Not a case_sub_status key of assessing: waiting_for_board.');
  });

  it('a stale write keeps the person’s text and offers a reload, never a merge', async () => {
    const sent = serve({ status: 409, data: { code: 'stale_write', detail: 'Someone else saved first.', currentVersion: 6 } });
    renderPanel(workflowOf(), WORKER);
    fireEvent.change(screen.getByRole('textbox', { name: 'Why' }), { target: { value: 'My own reasoning, not saved.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save assessment' }));

    expect(await screen.findByRole('button', { name: 'Reload their version' })).toBeInTheDocument();
    expect(screen.getByText(/Nothing of yours was saved or merged/)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Why' })).toHaveValue('My own reasoning, not saved.');
    expect(writes(sent)).toHaveLength(1);
  });
});

describe('"No" closes the case', () => {
  it('is offered to a holder of cases.work, and asks before it closes', async () => {
    const sent = serve();
    renderPanel(workflowOf(), WORKER);
    fireEvent.click(screen.getByRole('radio', { name: /^No/ }));
    expect(screen.getByText('Saving closes the case as not applicable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save assessment' }));

    const dialog = await screen.findByRole('dialog', { name: 'Close as not applicable?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep editing' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(writes(sent)).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Save assessment' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Save and close' }));
    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect(writes(sent)[0]?.body).toMatchObject({ applies: 'no', subStatus: null });
  });

  it('is not offered to someone who contributes but does not work cases, who is told whom to ask', () => {
    serve();
    renderPanel(workflowOf(), CONTRIBUTOR);
    expect(screen.getByRole('radio', { name: 'Yes' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /^No/ })).not.toBeInTheDocument();
    expect(screen.getByText('Saying it does not apply closes the case. Ask the case owner.')).toBeInTheDocument();
  });

  it('is not offered while the case is being implemented, which "No" cannot close', () => {
    serve();
    renderPanel(workflowOf({ category: 'implementing', subStatus: null }), WORKER);
    expect(screen.getByRole('button', { name: 'Save assessment' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /^No/ })).not.toBeInTheDocument();
  });
});

describe('read-only', () => {
  it('without cases.contribute: the saved facts, no control and no request', () => {
    const sent = serve();
    renderPanel(workflowOf(), ['cases.read', 'cases.work']);
    expect(screen.getByText('We pay two research providers from our own account.')).toBeInTheDocument();
    expect(screen.getByText('30 Sept 2026')).toBeInTheDocument();
    expect(screen.getByText('M, weeks of work')).toBeInTheDocument();
    expect(screen.getByText(/^Version 2, by Johan Berg, 19 Sept 2026/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(panelRequests(sent)).toHaveLength(0);
  });

  it('for everyone from waiting for sign-off on', () => {
    serve();
    renderPanel(workflowOf({ category: 'signoff', allowedTransitions: ['implementing', 'closed'] }), WORKER);
    expect(screen.getByText('Written criteria for the annual quality assessment.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('a closed case that never reached the assessment shows no panel', () => {
    serve();
    const { container } = render(<AssessmentPanel change={CHANGE} workflow={workflowOf({ category: 'closed', assessment: null })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
