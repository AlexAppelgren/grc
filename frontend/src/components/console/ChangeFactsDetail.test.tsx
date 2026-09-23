import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Suspense, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import ConsoleChangeFactsDetailPage from '@/app/(console)/console/change-facts/[changeId]/page';
import { ChangeFactsDetail } from '@/components/console/ChangeFactsDetail';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';

// One change in the console (WAT-03, WAT-04): the facts an agent put forward
// with their confidence and their marker, the corrections an editor makes, and
// the confirmation a person gives with a passkey, and the two things this page
// must get right — a machine's confirmation never reads as a person's, and it
// holds nothing of a bank's.

const ME_PATH = '/api/v1/me';
const CHANGES_PATH = '/api/v1/console/changes';
const PATCH_PATH = '/api/v1/changes/c1';
const LINKS_PATH = '/api/v1/changes/c1/obligations';
const CONFIRM_PATH = '/api/v1/changes/c1/confirmation';
const TERMS_PATH = '/api/v1/taxonomy/terms';

// Two terms share the key `securities` in different dimensions; the change's term is told
// apart by its label, which the change and the list both answer in the reader's language.
const TERMS = [
  { id: 't-securities', key: 'securities', label: 'Securities', dimension: { key: 'regime' } },
  { id: 't-other', key: 'securities', label: 'Securities services', dimension: { key: 'service_type' } },
];

const CHANGE_TYPES = [
  { key: 'adopted', kind: 'adopted', label: 'Adopted', labels: {}, usageNote: '', sortOrder: 1, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {} },
  { key: 'consultation', kind: 'proposal', label: 'Consultation', labels: {}, usageNote: '', sortOrder: 2, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {} },
];
const FLAGS = [
  { key: 'advice_perimeter', kind: null, label: 'Advice perimeter', labels: {}, usageNote: '', sortOrder: 1, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {} },
  { key: 'inducements', kind: null, label: 'Inducements', labels: {}, usageNote: '', sortOrder: 2, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {} },
];

const fact = (key: string, label: string, confidence: number | null, suggested: boolean) => ({ ref: { key, kind: null, label }, confidence, suggested });

const link = (obligationId: string, title: string, confidence: number | null, confirmed: boolean) => ({
  obligationId,
  title,
  instrumentShortName: 'FFFS 2017:2',
  refLabel: '9 kap. 6 §',
  origin: 'agent',
  confidence,
  confirmed,
});

const change = {
  id: 'c1',
  stableKey: 'fi-2026-research',
  title: 'FI adopts amended rules on paying for investment research',
  changeType: fact('adopted', 'Adopted', null, true),
  authorityLabel: 'Finansinspektionen',
  authorityId: 'a1',
  publishedOn: '2026-09-15',
  publishedPrecision: 'day',
  status: 'active',
  flags: [fact('advice_perimeter', 'Advice perimeter', 0.64, true)],
  terms: [fact('securities', 'Securities', 0.81, true)],
  obligations: [link('o1', 'Pay for third-party research only under the permitted models', 0.86, false)],
  unconfirmedCount: 4,
  firstSeenAt: '2026-09-16T06:02:00Z',
};

const editor = {
  user: { id: 'u10', email: 'editor@bleqq.test', name: 'Ida Holm', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['proposals.review', 'library_vocab.manage', 'sources.manage', 'eval.manage'],
  platformRoles: [{ key: 'library_editor', kind: null, label: 'Library editor' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

function server(rows: Answer, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: editor };
    if (sent.path === '/api/v1/vocab/change_type') return { status: 200, data: { items: CHANGE_TYPES, total: 2 } };
    if (sent.path === '/api/v1/vocab/flag') return { status: 200, data: { items: FLAGS, total: 2 } };
    if (sent.path === TERMS_PATH) return { status: 200, data: { items: TERMS, total: TERMS.length } };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === CHANGES_PATH && sent.method === 'get') return rows;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const page = (items: unknown[]): Answer => ({ status: 200, data: { items, total: items.length } });
const typeRow = () => document.querySelector('[data-fact="Change type"]') as HTMLElement;
const scopeRow = () => document.querySelector('[data-fact="Scope"]') as HTMLElement;

describe('console change facts detail', () => {
  beforeEach(() => {
    resetApiForTests();
    setStepUpHandler(null);
  });

  it('shows every fact with its confidence and its suggestion marker', async () => {
    server(page([change]));
    renderIn(<ChangeFactsDetail changeId="c1" />);

    expect(await screen.findByRole('heading', { level: 1, name: change.title })).toBeInTheDocument();
    const typeRow = document.querySelector('[data-fact="Change type"]') as HTMLElement;
    expect(within(typeRow).getByText('Adopted')).toBeInTheDocument();
    expect(within(typeRow).getByText('Suggested by the agent')).toBeInTheDocument();

    const flagRow = document.querySelector('[data-fact="Flags"]') as HTMLElement;
    expect(within(flagRow).getByText('Advice perimeter')).toBeInTheDocument();
    expect(within(flagRow).getByText('Suggested by the agent, confidence 0.64')).toBeInTheDocument();

    const scopeRow = document.querySelector('[data-fact="Scope"]') as HTMLElement;
    expect(within(scopeRow).getByText('Securities')).toBeInTheDocument();
    expect(within(scopeRow).getByText('Suggested by the agent, confidence 0.81')).toBeInTheDocument();

    const obligation = document.querySelector('[data-obligation-id="o1"]') as HTMLElement;
    expect(within(obligation).getByText('Suggested by the agent, confidence 0.86')).toBeInTheDocument();
  });

  it('confirms a suggested type by its key, after a passkey, and the fact then reads confirmed by a person', async () => {
    let current: Record<string, unknown> = change;
    let answered = 0;
    const sent = server(page([current]), (s) => {
      if (s.path === CONFIRM_PATH && s.method === 'post') {
        answered += 1;
        // The route asks the person to step up first; the client runs the passkey and retries once.
        if (answered === 1) return { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } };
        current = { ...current, changeType: { ...fact('adopted', 'Adopted', null, false), confirmedOrigin: 'user' } };
        return { status: 200, data: current };
      }
      if (s.path === CHANGES_PATH && s.method === 'get') return page([current]);
      return undefined;
    });
    let steppedUp = 0;
    setStepUpHandler(async () => {
      steppedUp += 1;
      return true;
    });
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(typeRow()).getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(within(typeRow()).getByText('Confirmed by a person for the library')).toBeInTheDocument());
    expect(steppedUp).toBe(1);
    expect(sent.filter((s) => s.path === CONFIRM_PATH).map((s) => s.body)).toEqual([
      { changeType: 'adopted', flags: [], termIds: [], obligationIds: [] },
      { changeType: 'adopted', flags: [], termIds: [], obligationIds: [] },
    ]);
    // Nothing is left to confirm on the type, so it offers no second confirmation.
    expect(within(typeRow()).queryByRole('button', { name: 'Confirm' })).toBeNull();
  });

  it('confirms the rest in one call: every suggested fact and link, a scope term by its id', async () => {
    const sent = server(page([change]), (s) => (s.path === CONFIRM_PATH ? { status: 200, data: change } : undefined));
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    // The scope's Confirm waits for the term's id, which the change names only by its key.
    await within(scopeRow()).findByRole('button', { name: 'Confirm' });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm the rest' }));

    await waitFor(() => expect(sent.filter((s) => s.path === CONFIRM_PATH)).toHaveLength(1));
    expect(sent.find((s) => s.path === CONFIRM_PATH)?.body).toEqual({
      changeType: 'adopted',
      flags: ['advice_perimeter'],
      termIds: ['t-securities'],
      obligationIds: ['o1'],
    });
  });

  it('confirms one obligation link for the library on its own', async () => {
    const sent = server(page([change]), (s) => (s.path === CONFIRM_PATH ? { status: 200, data: change } : undefined));
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(document.querySelector('[data-obligation-id="o1"]') as HTMLElement).getByRole('button', { name: 'Confirm for the library' }));
    await waitFor(() => expect(sent.filter((s) => s.path === CONFIRM_PATH)).toHaveLength(1));
    expect(sent.find((s) => s.path === CONFIRM_PATH)?.body).toEqual({ flags: [], termIds: [], obligationIds: ['o1'] });
  });

  it('reads a refusal from its code: a fact you filed yourself is somebody else’s to confirm', async () => {
    server(page([change]), (s) => (s.path === CONFIRM_PATH ? { status: 409, data: { code: 'own_suggestion', detail: 'You filed the type yourself.' } } : undefined));
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(typeRow()).getByRole('button', { name: 'Confirm' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-problem-code', 'own_suggestion');
    expect(alert).toHaveTextContent('You filed this yourself, so somebody else confirms it.');
    expect(alert).not.toHaveTextContent('You filed the type yourself.');
  });

  it('says nothing changed when the passkey step is cancelled', async () => {
    server(page([change]), (s) => (s.path === CONFIRM_PATH ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : undefined));
    setStepUpHandler(async () => false);
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(typeRow()).getByRole('button', { name: 'Confirm' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The action was not confirmed, so nothing changed.');
  });

  it('a fact a machine confirmed names both agents, never a person, and offers nothing left to confirm', async () => {
    const sweeper = { id: 'a1', key: 'watch-sweeper' };
    const confirmer = { id: 'a2', key: 'library-confirmer' };
    const machine = { confirmedOrigin: 'agent', suggestedByAgent: sweeper, confirmedByAgent: confirmer };
    const settled = {
      ...change,
      changeType: { ...fact('adopted', 'Adopted', 0.91, false), ...machine },
      // A set a person confirmed only in part still names the machine that confirmed the rest.
      flags: [{ ...fact('inducements', 'Inducements', 0.4, false), confirmedOrigin: 'user' }, { ...fact('advice_perimeter', 'Advice perimeter', 0.9, false), ...machine }],
      terms: [{ ...fact('securities', 'Securities', 0.81, false), ...machine }],
      obligations: [{ ...link('o1', 'Pay for third-party research only under the permitted models', 0.86, true), ...machine }],
      unconfirmedCount: 0,
    };
    server(page([settled]));
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    const machineLine = 'Machine-confirmed: suggested by watch-sweeper, confirmed by library-confirmer';
    expect(within(typeRow()).getByText(machineLine)).toBeInTheDocument();
    expect(within(scopeRow()).getByText(machineLine)).toBeInTheDocument();
    expect(within(document.querySelector('[data-fact="Flags"]') as HTMLElement).getByText(machineLine)).toBeInTheDocument();
    const obligation = document.querySelector('[data-obligation-id="o1"]') as HTMLElement;
    expect(within(obligation).getByText(machineLine)).toBeInTheDocument();
    expect(within(obligation).getByText('Machine-confirmed')).toHaveAttribute('data-pill', 'information');
    expect(screen.queryByText(/Confirmed by a person/)).toBeNull();
    expect(screen.queryByRole('button', { name: /^Confirm/ })).toBeNull();
    expect(screen.queryByText(/asks for your passkey/)).toBeNull();
  });

  it('names the agent that suggested a fact', async () => {
    server(page([{ ...change, changeType: { ...fact('adopted', 'Adopted', 0.91, true), suggestedByAgent: { id: 'a1', key: 'watch-sweeper' } } }]));
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });
    expect(within(typeRow()).getByText('Suggested by watch-sweeper, confidence 0.91')).toBeInTheDocument();
  });

  it('corrects the change type against the real route and shows it without a reload', async () => {
    let current = change;
    const sent = server(page([current]), (s) => {
      if (s.path === PATCH_PATH && s.method === 'patch') {
        current = { ...current, changeType: fact('consultation', 'Consultation', null, true) };
        return { status: 200, data: {} };
      }
      if (s.path === CHANGES_PATH && s.method === 'get') return page([current]);
      return undefined;
    });
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(document.querySelector('[data-fact="Change type"]') as HTMLElement).getByRole('button', { name: 'Correct' }));
    await screen.findByRole('option', { name: 'Consultation' });
    fireEvent.change(screen.getByLabelText('Change type'), { target: { value: 'consultation' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save the type' }));

    await waitFor(() => expect(within(document.querySelector('[data-fact="Change type"]') as HTMLElement).getByText('Consultation')).toBeInTheDocument());
    expect(sent.filter((s) => s.method === 'patch').map((s) => [s.path, s.body])).toEqual([[PATCH_PATH, { changeType: 'consultation' }]]);
  });

  it('sends the whole flag set, never a delta', async () => {
    const sent = server(page([change]), (s) => (s.path === PATCH_PATH ? { status: 200, data: {} } : undefined));
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(document.querySelector('[data-fact="Flags"]') as HTMLElement).getByRole('button', { name: 'Correct' }));
    fireEvent.click(await screen.findByLabelText('Inducements'));
    fireEvent.click(screen.getByLabelText('Advice perimeter'));
    fireEvent.click(screen.getByRole('button', { name: 'Save the flags' }));

    await waitFor(() => expect(sent.filter((s) => s.method === 'patch')).toHaveLength(1));
    expect(sent.find((s) => s.method === 'patch')?.body).toEqual({ flags: ['inducements'] });
  });

  it('reads a 422 unknown_key from its code and offers the valid keys, never the sentence', async () => {
    server(page([change]), (s) =>
      s.path === PATCH_PATH ? { status: 422, data: { code: 'unknown_key', detail: "'adopted' is not a change_type. Valid values: consultation." } } : undefined,
    );
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(document.querySelector('[data-fact="Change type"]') as HTMLElement).getByRole('button', { name: 'Correct' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save the type' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-problem-code', 'unknown_key');
    expect(alert).toHaveTextContent('That term is no longer on the list.');
    expect(alert).not.toHaveTextContent('is not a change_type');
    // The valid keys are the picker itself, which is the vocabulary.
    expect(within(document.querySelector('[data-correct-type]') as HTMLElement).getByRole('option', { name: 'Consultation' })).toBeInTheDocument();
  });

  it('removes an obligation link by sending the set that remains', async () => {
    const two = { ...change, obligations: [change.obligations[0]!, link('o2', 'Disclose all costs and charges', 0.41, false)] };
    const sent = server(page([two]), (s) => (s.path === LINKS_PATH ? { status: 200, data: [] } : undefined));
    renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    fireEvent.click(within(document.querySelector('[data-obligation-id="o1"]') as HTMLElement).getByRole('button', { name: 'Remove the link' }));
    await waitFor(() => expect(sent.filter((s) => s.method === 'put')).toHaveLength(1));
    expect(sent.find((s) => s.method === 'put')?.body).toEqual([{ obligationId: 'o2', confidence: 0.41 }]);
  });

  it('reads the library alone: no bank is asked for, and no case or footprint verdict is shown', async () => {
    const sent = server(page([change]));
    const { container } = renderIn(<ChangeFactsDetail changeId="c1" />);
    await screen.findByRole('heading', { level: 1, name: change.title });

    // GET /changes/{changeId} would answer the reader's own case and footprint
    // verdict beside the library record; the console asks for neither it nor
    // anything else under a bank (NFR-01).
    // The term list is the library's too: the scope's Confirm names a term by its id.
    await waitFor(() => expect([...new Set(sent.map((s) => s.path))].sort()).toEqual([CHANGES_PATH, ME_PATH, REFRESH_PATH, TERMS_PATH].sort()));
    expect(container.querySelector('[data-case-id], [data-footprint]')).toBeNull();
  });

  it('is not found when no change the console can reach has that id', async () => {
    server(page([change]));
    renderIn(<ChangeFactsDetail changeId="nope" />);
    expect(await screen.findByRole('heading', { name: 'Not found' })).toBeInTheDocument();
  });

  it('offers a retry when the change could not be read', async () => {
    server({ status: 500, data: { code: 'server_error', detail: 'no' } });
    renderIn(<ChangeFactsDetail changeId="c1" />);
    expect(await screen.findByText('Could not load this change')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('shows the Restricted screen, naming the grant, to a console session without proposals.review', async () => {
    server(page([change]));
    await act(async () => {
      renderIn(
        <Suspense fallback={null}>
          <PermissionsProvider permissions={['tenants.manage']}>
            <ConsoleChangeFactsDetailPage params={Promise.resolve({ changeId: 'c1' })} />
          </PermissionsProvider>
        </Suspense>,
      );
    });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Needs proposals review');
  });
});
