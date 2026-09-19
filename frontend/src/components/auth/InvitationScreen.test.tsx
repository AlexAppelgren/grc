import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { metadata } from '@/app/(auth)/invite/page';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

import { EnrolScreen, INVITATION_ENROL_PATH } from './EnrolScreen';
import { InvitationScreen, replaceWithEnrol, takeTokenFromHash } from './InvitationScreen';

// The emailed link is /invite#<token>: a fragment never reaches any server,
// proxy or Referer (security review F29). The screen reads it, clears it from
// the address before any request, and posts it in the body.
//
// The invitation path asks for the code alone: the link's token names the
// account and is verified with the code (POST /auth/invitations/verify). The
// token lives in React state only, never in the address, storage or a log
// (chunk 1 review F28), and never leaves through a Referer header.

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));
vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: ComponentProps<'a'> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const TOKEN = 'secret-invitation-token-42';
const ENROLMENT = { accessToken: 'enrol', sessionKind: 'enrolment', expiresIn: 600 };

function server(verify: (sent: Sent) => Answer = () => ({ status: 200, data: ENROLMENT }), open: () => Answer = () => ({ status: 202, data: {} })) {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 401 };
    if (sent.path.endsWith('/open')) return open();
    if (sent.path.endsWith('/verify')) return verify(sent);
    if (sent.path === '/api/v1/me') return { status: 200, data: { enrolmentPending: true } };
    return { status: 202, data: {} };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(
    <Query>
      <LocaleProvider locale="en">{node}</LocaleProvider>
    </Query>,
  );
}

function typeCode(code: string) {
  fireEvent.change(screen.getByLabelText('Code'), { target: { value: code } });
}

function everythingStored(): string {
  const all: string[] = [window.location.href, document.cookie];
  for (const store of [window.localStorage, window.sessionStorage]) {
    for (let i = 0; i < store.length; i += 1) {
      const key = store.key(i) ?? '';
      all.push(key, store.getItem(key) ?? '');
    }
  }
  return all.join('\n');
}

describe('the invitation address', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is replaced by /enrol, so no history entry holds the token', () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    replaceWithEnrol();
    expect(replaceState).toHaveBeenCalledWith(null, '', INVITATION_ENROL_PATH);
    expect(INVITATION_ENROL_PATH).not.toContain(TOKEN);
    // Replaced, never pushed: the back button must not reach the token either.
    expect(vi.spyOn(window.history, 'pushState')).not.toHaveBeenCalled();
  });

  it('leaves a runtime without history alone rather than throwing', () => {
    const original = window.history;
    Object.defineProperty(window, 'history', { value: undefined, configurable: true });
    try {
      expect(() => replaceWithEnrol()).not.toThrow();
    } finally {
      Object.defineProperty(window, 'history', { value: original, configurable: true });
    }
  });

  it('takes the token from the fragment and clears the address in the same step', () => {
    window.history.replaceState(null, '', `/invite#${TOKEN}`);
    expect(takeTokenFromHash()).toBe(TOKEN);
    expect(window.location.hash).toBe('');
    expect(window.location.pathname + window.location.search).toBe(INVITATION_ENROL_PATH);
    // A second read finds nothing: the token now lives only where the caller keeps it.
    expect(takeTokenFromHash()).toBeNull();
  });

  it('finds no token when the link has no fragment, and still leaves the invite address', () => {
    window.history.replaceState(null, '', '/invite');
    expect(takeTokenFromHash()).toBeNull();
    expect(window.location.pathname + window.location.search).toBe(INVITATION_ENROL_PATH);
  });

  it('sends no Referer from the invite route', () => {
    // Next renders this as <meta name="referrer" content="no-referrer">.
    expect(metadata.referrer).toBe('no-referrer');
  });
});

describe('opening the invitation', () => {
  beforeEach(() => {
    resetApiForTests();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('clears the fragment before any request, then posts the token in the body of /open', async () => {
    window.history.replaceState(null, '', `/invite#${TOKEN}`);
    const addressAtRequest: string[] = [];
    const sent = installAdapter((request) => {
      addressAtRequest.push(window.location.href);
      if (request.path === REFRESH_PATH) return { status: 401 };
      return { status: 202, data: {} };
    });
    renderIn(<InvitationScreen />);
    await screen.findByRole('heading', { level: 1, name: 'Enter your code' });
    const open = sent.find((s) => s.path === '/api/v1/auth/invitations/open');
    expect(open?.body).toEqual({ token: TOKEN });
    expect(sent.map((s) => s.path).join(' ')).not.toContain(TOKEN);
    expect(addressAtRequest.length).toBeGreaterThan(0);
    for (const href of addressAtRequest) expect(href).not.toContain(TOKEN);
    expect(window.location.hash).toBe('');
    expect(everythingStored()).not.toContain(TOKEN);
  });

  it('asks for the link again when the address carries no token, and sends nothing', async () => {
    window.history.replaceState(null, '', '/invite');
    const sent = server();
    renderIn(<InvitationScreen />);
    await screen.findByText('To get a code, open the link in your invitation email again.');
    expect(sent.some((s) => s.path === '/api/v1/auth/invitations/open')).toBe(false);
  });
});

describe('the invitation code step', () => {
  beforeEach(() => {
    resetApiForTests();
    window.history.replaceState(null, '', `/invite#${TOKEN}`);
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('asks for the code alone and verifies it with the token held in memory, never in the URL or storage', async () => {
    const log = vi.spyOn(console, 'log');
    const sent = server();
    renderIn(<InvitationScreen />);
    await screen.findByRole('heading', { level: 1, name: 'Enter your code' });
    expect(screen.queryByLabelText('Email address')).toBeNull();
    expect(window.location.pathname + window.location.search).toBe(INVITATION_ENROL_PATH);
    typeCode('123456');
    await waitFor(() => expect(sent.some((s) => s.path === '/api/v1/auth/invitations/verify')).toBe(true));
    const verify = sent.find((s) => s.path === '/api/v1/auth/invitations/verify');
    expect(verify?.body).toEqual({ token: TOKEN, code: '123456' });
    // The token travels in a body only: no request path, the address bar or any storage holds it.
    expect(sent.map((s) => s.path).join(' ')).not.toContain(TOKEN);
    expect(everythingStored()).not.toContain(TOKEN);
    expect(JSON.stringify(log.mock.calls)).not.toContain(TOKEN);
    await screen.findByRole('heading', { level: 1, name: 'Create your passkey' });
  });

  it('says a wrong code is not right, and "Send a new code" opens the same invitation again', async () => {
    const sent = server(() => ({ status: 400, data: { code: 'invalid_code', detail: 'That code is not right.' } }));
    renderIn(<InvitationScreen />);
    await screen.findByRole('heading', { level: 1, name: 'Enter your code' });
    typeCode('111111');
    await screen.findByText('That code is not right.');
    expect(screen.getByLabelText('Code')).toHaveAttribute('aria-invalid', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Send a new code' }));
    await screen.findByText('A new code is on its way to the invited address.');
    const opens = sent.filter((s) => s.path === '/api/v1/auth/invitations/open');
    expect(opens).toHaveLength(2);
    expect(opens.map((s) => s.body)).toEqual([{ token: TOKEN }, { token: TOKEN }]);
  });

  it('asks for all six digits before verifying, and locks after too many attempts', async () => {
    const sent = server(() => ({ status: 400, data: { code: 'code_locked', detail: 'Too many attempts.' } }));
    renderIn(<InvitationScreen />);
    await screen.findByRole('heading', { level: 1, name: 'Enter your code' });
    typeCode('123');
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Enter the six-digit code.')).toBeVisible();
    expect(sent.some((s) => s.path.endsWith('/verify'))).toBe(false);
    typeCode('123456');
    await screen.findByText('Too many attempts. Send a new code and try again.');
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('shows the invitation as no longer valid when verify or a new code answers 410', async () => {
    server(() => ({ status: 410, data: { code: 'invitation_expired', detail: 'Gone.' } }));
    renderIn(<InvitationScreen />);
    await screen.findByRole('heading', { level: 1, name: 'Enter your code' });
    typeCode('123456');
    await screen.findByText('This invitation is no longer valid. Ask your administrator to send a new one.');
    expect(screen.getByRole('button', { name: 'Send a new code' })).toBeDisabled();
  });

  it('shows other failures of verify and of a new code as problems', async () => {
    let opens = 0;
    server(
      () => ({ status: 500, data: { detail: 'Boom.' } }),
      () => {
        opens += 1;
        return opens === 1 ? { status: 202, data: {} } : { status: 500, data: { detail: 'Boom.' } };
      },
    );
    renderIn(<InvitationScreen />);
    await screen.findByRole('heading', { level: 1, name: 'Enter your code' });
    fireEvent.click(screen.getByRole('button', { name: 'Send a new code' }));
    await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
    typeCode('123456');
    await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
  });

  it('after a reload the token is gone: it asks to open the link again, with no email field', async () => {
    server();
    window.history.replaceState(null, '', INVITATION_ENROL_PATH);
    renderIn(<EnrolScreen />);
    await screen.findByText('To get a code, open the link in your invitation email again.');
    expect(screen.queryByLabelText('Email address')).toBeNull();
    expect(screen.queryByLabelText('Code')).toBeNull();
    expect(screen.getByRole('link', { name: 'Go to sign in' })).toHaveAttribute('href', '/sign-in');
  });

  it('shows the expired and error states when the link cannot be opened', async () => {
    let status = 410;
    server(undefined, () => ({ status, data: {} }));
    const view = renderIn(<InvitationScreen />);
    await screen.findByText('This invitation is no longer valid. Ask your administrator to send a new one.');
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
    view.unmount();
    status = 500;
    window.history.replaceState(null, '', `/invite#${TOKEN}`);
    renderIn(<InvitationScreen />);
    await screen.findByText('We could not open the invitation. Check your connection and try again.');
    status = 202;
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    });
    await screen.findByRole('heading', { level: 1, name: 'Enter your code' });
  });
});

describe('the sign-in path ("First time here?")', () => {
  beforeEach(() => {
    resetApiForTests();
    window.history.replaceState(null, '', '/enrol');
  });

  it('asks for the address and the code, and a new code gets the neutral answer', async () => {
    const sent = server();
    renderIn(<EnrolScreen />);
    await screen.findByLabelText('Email address');
    fireEvent.click(screen.getByRole('button', { name: 'Send a new code' }));
    expect(screen.getByText('Enter your email address and the six-digit code.')).toBeVisible();
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: ' anna@example-bank.test ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send a new code' }));
    await screen.findByText('If that address is awaiting enrolment, a new code is on its way.');
    typeCode('123456');
    await waitFor(() => expect(sent.some((s) => s.path === '/api/v1/auth/code/verify')).toBe(true));
    expect(sent.find((s) => s.path === '/api/v1/auth/code/verify')?.body).toEqual({ email: 'anna@example-bank.test', code: '123456' });
  });

  it('does not verify a complete code without the address', async () => {
    const sent = server();
    renderIn(<EnrolScreen />);
    await screen.findByLabelText('Email address');
    typeCode('123456');
    expect(screen.getByText('Enter your email address and the six-digit code.')).toBeVisible();
    expect(sent.some((s) => s.path.endsWith('/verify'))).toBe(false);
  });
});
