import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { CaseAction, CaseWorkflow } from '@/features/cases/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ActionsPanel, tenantToday } from './ActionsPanel';

// The Actions panel (design/screens/tenant-change.html, "Actions"; CAS-04):
// days left in tabular numerals and overdue as a negative pill; the add row,
// completion and remove with its confirm; the lock while the case waits for
// sign-off; a contributor completes but never adds or removes; every refusal
// in place, from the server's answer.

const ZONE = 'Europe/Stockholm';
const SESSION = { user: { locale: 'en' }, tenant: { timezone: ZONE }, enrolmentPending: false, permissions: [] };
const WORKER = ['cases.read', 'cases.work', 'cases.contribute'];
const CONTRIBUTOR = ['cases.read', 'cases.contribute'];
const READER = ['cases.read'];

/** A plain date `offset` days from the tenant-local today. */
function day(offset: number): string {
  const today = tenantToday(ZONE);
  return new Date(today.getTime() + offset * 86_400_000).toISOString().slice(0, 10);
}

const person = (id: string, name: string) => ({ id, name });

function action(id: string, title: string, dueOffset: number, done = false): CaseAction {
  return {
    id,
    changeId: 'c-1',
    title,
    owner: person('u-1', 'Johan Berg'),
    dueDate: day(dueOffset),
    done,
    doneAt: done ? `${day(-1)}T09:00:00Z` : null,
    doneBy: done ? person('u-1', 'Johan Berg') : null,
    createdAt: '2026-09-18T10:12:00Z',
    version: 2,
  };
}

const LATE = action('a-1', 'Write the criteria for the annual research assessment', -4);
const AHEAD = action('a-2', 'Get the investment committee to adopt the criteria', 11);
const DONE = action('a-3', 'List the research providers paid from our own account', -2, true);

function workflow(category: CaseWorkflow['category'], openActionCount = 2): CaseWorkflow {
  return { category, version: 6, owner: person('u-2', 'Sara Lindqvist'), openActionCount } as CaseWorkflow;
}

function serve(route: (sent: Sent) => Answer | undefined, items: CaseAction[] = [LATE, AHEAD, DONE]): Sent[] {
  return installAdapter((sent) => {
    const scripted = route(sent);
    if (scripted !== undefined) return scripted;
    if (sent.method === 'get' && sent.path === '/api/v1/changes/c-1/actions') return { status: 200, data: { items, total: items.length } };
    return { status: 200, data: SESSION };
  });
}

function renderPanel(permissions: string[], category: CaseWorkflow['category'] = 'implementing'): void {
  const { wrapper: Query } = queryWrapper();
  const tree: ReactNode = (
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <ActionsPanel change={{ id: 'c-1' } as never} workflow={workflow(category)} />
        </PermissionsProvider>
      </LocaleProvider>
    </Query>
  );
  render(tree);
}

const writes = (sent: Sent[]) => sent.filter((request) => request.method !== 'get').map((request) => [request.method, request.path, request.body]);
const row = (id: string) => document.querySelector(`[data-action="${id}"]`) as HTMLElement;

beforeEach(() => {
  cleanup();
  resetApiForTests();
  tokenStore.set('tok');
});

describe('tenantToday', () => {
  it('is the calendar day in the tenant’s zone, not the machine’s', () => {
    const lateEvening = new Date('2026-09-19T22:30:00Z');
    expect(tenantToday('Europe/Stockholm', lateEvening).toISOString()).toBe('2026-09-20T00:00:00.000Z');
    expect(tenantToday('UTC', lateEvening).toISOString()).toBe('2026-09-19T00:00:00.000Z');
  });
});

describe('the list', () => {
  it('shows owner, due date, days left and late in tabular numerals, overdue as a negative pill, and who completed', async () => {
    serve(() => undefined);
    renderPanel(READER);
    await screen.findByText(LATE.title);

    const late = within(row('a-1'));
    expect(late.getByText('Johan Berg')).toBeInTheDocument();
    expect(late.getByText('4 days late')).toHaveClass('tabular-nums');
    expect(late.getByText('Overdue').closest('[data-pill]')).toHaveAttribute('data-pill', 'negative');

    const ahead = within(row('a-2'));
    expect(ahead.getByText('11 days left')).toHaveClass('tabular-nums');
    expect(ahead.queryByText('Overdue')).toBeNull();

    const done = within(row('a-3'));
    expect(done.getByRole('checkbox')).toBeChecked();
    expect(done.getByText(/^Done .* by Johan Berg$/)).toBeInTheDocument();
    expect(done.queryByText('Overdue')).toBeNull();
    expect(screen.getByText('2 of 3 open')).toBeInTheDocument();
  });

  it('says what to do when the case has no action yet', async () => {
    serve(() => undefined, []);
    renderPanel(WORKER, 'assessing');
    expect(await screen.findByText('No actions yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add action' })).toBeInTheDocument();
  });

  it('shows the error in place with a retry', async () => {
    serve((sent) => (sent.path.endsWith('/actions') ? { status: 500, data: { code: 'server_error' } } : undefined));
    renderPanel(READER);
    expect(await screen.findByText('Could not load the actions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('who may do what', () => {
  it('a reader sees the list with every box off and no control', async () => {
    serve(() => undefined);
    renderPanel(READER);
    await screen.findByText(LATE.title);
    for (const box of screen.getAllByRole('checkbox')) expect(box).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add action' })).toBeNull();
  });

  it('a contributor completes and reopens with the action’s own write, but never adds or removes', async () => {
    const sent = serve((request) => (request.method === 'patch' ? { status: 200, data: { ...LATE, done: true, version: 3 } } : undefined));
    renderPanel(CONTRIBUTOR);
    await screen.findByText(LATE.title);
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add action' })).toBeNull();

    fireEvent.click(within(row('a-1')).getByRole('checkbox'));
    await waitFor(() => expect(writes(sent)).toEqual([['patch', '/api/v1/actions/a-1', { done: true }]]));
    fireEvent.click(within(row('a-3')).getByRole('checkbox'));
    await waitFor(() => expect(writes(sent)[1]).toEqual(['patch', '/api/v1/actions/a-3', { done: false }]));
  });
});

describe('adding an action', () => {
  it('sends the title and due date, the case owner owning it, and clears the row', async () => {
    const sent = serve((request) => (request.method === 'post' ? { status: 201, data: AHEAD } : undefined));
    renderPanel(WORKER, 'assessing');
    await screen.findByText(LATE.title);
    expect(screen.getByText("Sara Lindqvist owns it, as the case's owner.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('New action'), { target: { value: 'Brief the investment committee' } });
    fireEvent.change(screen.getByLabelText('Due'), { target: { value: day(14) } });
    fireEvent.click(screen.getByRole('button', { name: 'Add action' }));
    await waitFor(() => expect(writes(sent)).toEqual([['post', '/api/v1/changes/c-1/actions', { title: 'Brief the investment committee', dueDate: day(14) }]]));
    await waitFor(() => expect(screen.getByLabelText('New action')).toHaveValue(''));
  });

  it('renders the server’s 422 against the title', async () => {
    serve((request) =>
      request.method === 'post'
        ? { status: 422, data: { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.title', message: 'too short' }] } }
        : undefined,
    );
    renderPanel(WORKER);
    await screen.findByText(LATE.title);
    fireEvent.click(screen.getByRole('button', { name: 'Add action' }));
    expect(await screen.findByText('Give the action a title.')).toBeInTheDocument();
    expect(screen.getByLabelText('New action')).toHaveAttribute('aria-invalid', 'true');
  });

  it('renders the cap’s 409 with the number from the answer', async () => {
    const detail = 'A case holds at most 50 actions. Remove one that is no longer needed first.';
    serve((request) => (request.method === 'post' ? { status: 409, data: { code: 'too_many_actions', detail } } : undefined));
    renderPanel(WORKER);
    await screen.findByText(LATE.title);
    fireEvent.change(screen.getByLabelText('New action'), { target: { value: 'One more' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add action' }));
    expect(await screen.findByText(detail)).toHaveAttribute('data-problem-code', 'too_many_actions');
  });
});

describe('removing an action', () => {
  it('asks first, then removes it with the action’s own write', async () => {
    const sent = serve((request) => (request.method === 'delete' ? { status: 204 } : undefined));
    renderPanel(WORKER);
    await screen.findByText(LATE.title);
    fireEvent.click(within(row('a-2')).getByRole('button', { name: 'Remove' }));

    const dialog = await screen.findByRole('dialog', { name: `Remove "${AHEAD.title}"?` });
    expect(writes(sent)).toEqual([]);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(writes(sent)).toEqual([['delete', '/api/v1/actions/a-2', null]]));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('Cancel removes nothing', async () => {
    const sent = serve(() => undefined);
    renderPanel(WORKER);
    await screen.findByText(LATE.title);
    fireEvent.click(within(row('a-2')).getByRole('button', { name: 'Remove' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);
  });
});

describe('the lock while the case waits for sign-off', () => {
  it('turns every control off and says why, even for a worker', async () => {
    serve(() => undefined);
    renderPanel(WORKER, 'signoff');
    await screen.findByText(LATE.title);
    expect(screen.getByText('Actions are locked while this case waits for sign-off. Sending it back unlocks them.')).toBeInTheDocument();
    for (const box of screen.getAllByRole('checkbox')) expect(box).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add action' })).toBeNull();
  });

  it('a closed case is read-only too', async () => {
    serve(() => undefined);
    renderPanel(WORKER, 'closed');
    await screen.findByText(LATE.title);
    for (const box of screen.getAllByRole('checkbox')) expect(box).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Add action' })).toBeNull();
  });

  it('a stale tab’s 409 actions_locked renders in place with a reload', async () => {
    serve((request) => (request.method === 'patch' ? { status: 409, data: { code: 'actions_locked', detail: 'Locked.' } } : undefined));
    renderPanel(WORKER);
    await screen.findByText(LATE.title);
    fireEvent.click(within(row('a-1')).getByRole('checkbox'));
    const refusal = await screen.findByText(/This case now waits for sign-off/);
    expect(refusal).toHaveAttribute('data-problem-code', 'actions_locked');
    expect(within(refusal).getByRole('button', { name: 'Reload to see it' })).toBeInTheDocument();
  });

  it('a 409 stale_write offers a reload and merges nothing', async () => {
    serve((request) => (request.method === 'patch' ? { status: 409, data: { code: 'stale_write', detail: 'Stale.', currentVersion: 4 } } : undefined));
    renderPanel(WORKER);
    await screen.findByText(LATE.title);
    fireEvent.click(within(row('a-1')).getByRole('checkbox'));
    const refusal = await screen.findByText(/Someone else saved this/);
    expect(within(refusal).getByRole('button', { name: 'Reload their version' })).toBeInTheDocument();
  });
});
