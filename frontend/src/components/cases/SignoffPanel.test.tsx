import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { CaseWorkflow } from '@/features/cases/types';
import type { ChangeDetail } from '@/features/watch/api';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { setStepUpHandler, tokenStore } from '@/shared/utils/api-client';

import { SignoffPanel } from './SignoffPanel';

// The sign-off panel of design/screens/tenant-change.html (CAS-06): Request
// sign-off while implementing, read off the server's canRequestSignoff and
// openActionCount; Sign off and close with a passkey, or Send back with a
// note, while it waits; both names once it is signed off. The panel decides
// nothing: every refusal is the server's code, said in words where it
// happened.

const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };
const MARIA = { id: 'u-maria', name: 'Maria Ek' };
const change = { id: 'c-1' } as ChangeDetail;

const implementing = {
  id: 'case-1',
  category: 'implementing',
  version: 4,
  canRequestSignoff: true,
  openActionCount: 0,
  signoffRequestedBy: null,
  signoffRequestedAt: null,
  signedOffBy: null,
  closeReason: null,
  closedAt: null,
  dismissedReason: null,
} as unknown as CaseWorkflow;

const waiting = {
  ...implementing,
  category: 'signoff',
  version: 5,
  canRequestSignoff: false,
  signoffRequestedBy: SARA,
  signoffRequestedAt: '2026-09-19T14:05:00Z',
} as CaseWorkflow;

const signedOff = {
  ...waiting,
  category: 'closed',
  version: 6,
  signedOffBy: MARIA,
  closeReason: { key: 'signed_off', kind: 'signed_off', label: 'Signed off' },
  closedAt: '2026-09-22T08:31:00Z',
} as CaseWorkflow;

function session(userId: string) {
  return {
    user: { id: userId, locale: 'en' },
    tenant: { timezone: 'Europe/Stockholm' },
    enrolmentPending: false,
    permissions: [],
  };
}

/** Reads answer the session of `me`; every write answers `write(sent, n)` for the n-th write. Returns the writes. */
function serve(write: (sent: Sent, n: number) => Answer, me = MARIA.id): () => Sent[] {
  let writes = 0;
  const sent = installAdapter((request) => (request.method === 'get' ? { status: 200, data: session(me) } : write(request, writes++)));
  return () => sent.filter((request) => request.method !== 'get');
}

function renderPanel(workflow: CaseWorkflow, permissions: string[]): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <SignoffPanel change={change} workflow={workflow} />
        </PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

const problem = (status: number, code: string, extra: Record<string, unknown> = {}): Answer => ({
  status,
  data: { status, code, title: '', detail: 'server words', ...extra },
});

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

describe('Request sign-off, while implementing', () => {
  it('is disabled with the open-action count as its reason when the server says it cannot be asked for', () => {
    serve(() => ({ status: 200 }));
    renderPanel({ ...implementing, canRequestSignoff: false, openActionCount: 2 }, ['cases.work']);
    const button = screen.getByRole('button', { name: 'Request sign-off' });
    expect(button).toBeDisabled();
    expect(screen.getByText('2 actions are still open.')).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-describedby', screen.getByText('2 actions are still open.').id);
  });

  it('with no open action, the reason it is disabled is the missing checked evidence', () => {
    serve(() => ({ status: 200 }));
    renderPanel({ ...implementing, canRequestSignoff: false }, ['cases.work']);
    expect(screen.getByRole('button', { name: 'Request sign-off' })).toBeDisabled();
    expect(screen.getByText('No evidence has been checked yet.')).toBeInTheDocument();
  });

  it('asks for sign-off on the change’s case, sending no body', async () => {
    const writes = serve(() => ({ status: 200, data: waiting }));
    renderPanel(implementing, ['cases.work']);
    expect(screen.getByText('Every action is done and there is evidence that has been checked. Someone else who can sign off then closes the case.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Request sign-off' }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toMatchObject({
      method: 'post',
      path: '/api/v1/changes/c-1/signoff/request',
    });
  });

  it('a stale 409 open_actions says how many actions the server counted, in place', async () => {
    serve(() =>
      problem(409, 'open_actions', {
        openActionCount: 1,
        cleanEvidenceCount: 1,
      }),
    );
    renderPanel(implementing, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Request sign-off' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('1 action is still open. Complete or remove it, then request sign-off.');
  });

  it('a stale 409 evidence_missing asks for checked evidence', async () => {
    serve(() =>
      problem(409, 'evidence_missing', {
        openActionCount: 0,
        cleanEvidenceCount: 0,
      }),
    );
    renderPanel(implementing, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Request sign-off' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Attach at least one piece of evidence, and wait until a file has been checked, then request sign-off.');
  });

  it('a stale_write offers a reload and never retries on its own', async () => {
    const writes = serve(() => problem(409, 'stale_write', { currentVersion: 5 }));
    renderPanel(implementing, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Request sign-off' }));
    expect(await screen.findByRole('button', { name: 'Reload their version' })).toBeInTheDocument();
    expect(writes()).toHaveLength(1);
  });

  it('without cases.work the reader sees where it stands and no control', () => {
    serve(() => ({ status: 200 }));
    renderPanel({ ...implementing, canRequestSignoff: false, openActionCount: 1 }, ['cases.read']);
    expect(screen.getByText('1 action is still open.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('Waiting for sign-off', () => {
  it('names who asked and when, and signs off with the optional note', async () => {
    const writes = serve(() => ({ status: 200, data: signedOff }));
    renderPanel(waiting, ['cases.signoff']);
    expect(await screen.findByText(/^Sara Lindqvist asked for sign-off on 19 Sept 2026, 16:05\. Read the assessment/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Note (optional)'), {
      target: { value: 'Criteria reviewed.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign off and close' }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toMatchObject({
      method: 'post',
      path: '/api/v1/changes/c-1/signoff/approve',
      body: { note: 'Criteria reviewed.' },
    });
  });

  it('sends the sign-off again once the passkey prompt succeeds', async () => {
    const writes = serve((_, n) => (n === 0 ? problem(403, 'step_up_required') : { status: 200, data: signedOff }));
    const prompts: number[] = [];
    setStepUpHandler(() => {
      prompts.push(1);
      return Promise.resolve(true);
    });
    renderPanel(waiting, ['cases.signoff']);
    fireEvent.click(await screen.findByRole('button', { name: 'Sign off and close' }));
    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(prompts).toHaveLength(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('a cancelled passkey prompt leaves the case waiting, and says so', async () => {
    serve(() => problem(403, 'step_up_required'));
    setStepUpHandler(() => Promise.resolve(false));
    renderPanel(waiting, ['cases.signoff']);
    fireEvent.click(await screen.findByRole('button', { name: 'Sign off and close' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The case was not signed off. Sign off and close needs your passkey.');
  });

  it('the requester is told in words, from the code, that a second person has to sign off', async () => {
    serve(() => problem(409, 'four_eyes_violation'), SARA.id);
    renderPanel(waiting, ['cases.work', 'cases.signoff']);
    expect(await screen.findByText('You asked for sign-off on 19 Sept 2026, 16:05. Someone else who can sign off has to give it.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Sign off and close' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("You asked for this sign-off, so you can't give it. A second person has to sign off.");
    expect(screen.getByRole('alert')).not.toHaveTextContent('server words');
  });

  it('Send back needs a note, and sends it', async () => {
    const writes = serve(() => ({
      status: 200,
      data: { ...implementing, version: 6 },
    }));
    renderPanel(waiting, ['cases.signoff']);
    fireEvent.click(await screen.findByRole('button', { name: 'Send back' }));
    const dialog = await screen.findByRole('dialog', {
      name: 'Send back for more work?',
    });
    expect(dialog).toHaveTextContent('Sara Lindqvist can ask for sign-off again when it is ready.');
    const submit = screen.getAllByRole('button', { name: 'Send back' }).find((button) => dialog.contains(button))!;
    fireEvent.click(submit);
    expect(await screen.findByText('Say what needs to change.')).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
    fireEvent.change(screen.getByLabelText('What needs to change'), {
      target: { value: 'Attach the adopted criteria.' },
    });
    fireEvent.click(submit);
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toMatchObject({
      method: 'post',
      path: '/api/v1/changes/c-1/signoff/send-back',
      body: { note: 'Attach the adopted criteria.' },
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('without cases.signoff the reader sees who asked and no control', async () => {
    serve(() => ({ status: 200 }));
    renderPanel(waiting, ['cases.work']);
    expect(await screen.findByText('Sara Lindqvist asked for sign-off on 19 Sept 2026, 16:05. Someone who can sign off will pick it up.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});

describe('Signed off', () => {
  it('shows both names with their dates and no control', () => {
    serve(() => ({ status: 200 }));
    renderPanel(signedOff, ['cases.work', 'cases.signoff', 'cases.triage']);
    expect(screen.getByRole('heading', { name: 'Closed' })).toBeInTheDocument();
    expect(screen.getByText('Signed off by').nextElementSibling).toHaveTextContent('Maria Ek, 22 Sept 2026');
    expect(screen.getByText('Asked for by').nextElementSibling).toHaveTextContent('Sara Lindqvist, 19 Sept 2026');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
