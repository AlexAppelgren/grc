import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { SecurityPolicyScreen } from '@/components/admin/SecurityPolicyScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';

// The bank's session limits (ID-08, ADM-01): each field shows the platform
// maximum beside it, a save goes through the passkey step-up (the api client
// opens the prompt on step_up_required), and the server's 422
// above_platform_maximum renders under the field it names. There is no passkey
// policy on this page (D-100).

const PATH = '/api/v1/tenant/security-policy';

const policy = {
  sessionIdleMinutes: null,
  sessionAbsoluteHours: 8,
  sessionIdleMinutesDefault: 30,
  sessionIdleMinutesMax: 480,
  sessionAbsoluteHoursDefault: 12,
  sessionAbsoluteHoursMax: 24,
  updatedAt: null,
  updatedBy: null,
};

type Answer = { status: number; data: unknown };

const stepUpRequired: Answer = { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.', status: 403 } };

/** The server: the policy on GET, and each PUT answered by `answer` (by default, the body echoed into the policy). */
function server(answer?: (count: number, body: unknown) => Answer): Sent[] {
  let puts = 0;
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === PATH && sent.method === 'get') return { status: 200, data: policy };
    if (sent.path === PATH && sent.method === 'put') {
      puts += 1;
      return answer?.(puts, sent.body) ?? { status: 200, data: { ...policy, ...(sent.body as object) } };
    }
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

const puts = (sent: Sent[]) => sent.filter((s) => s.method === 'put' && s.path === PATH).map((s) => s.body);

const IDLE = 'Sign out after this long without activity, in minutes';
const ABSOLUTE = 'Sign out after this long in all, in hours';

async function renderScreen(): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <SecurityPolicyScreen />
    </Query>,
  );
  await screen.findByLabelText(IDLE);
}

beforeEach(() => {
  resetApiForTests();
});

describe('the security page', () => {
  it('shows the limits in force with the platform maximum beside each, and no passkey policy', async () => {
    server();
    await renderScreen();
    expect(screen.getByLabelText(IDLE)).toHaveValue('30');
    expect(screen.getByLabelText(ABSOLUTE)).toHaveValue('8');
    expect(screen.getByText('At most 480 minutes. Leave it empty for the platform default of 30.')).toBeInTheDocument();
    expect(screen.getByText('At most 24 hours. Leave it empty for the platform default of 12.')).toBeInTheDocument();
    expect(screen.getByText('Saving asks for your passkey.')).toBeInTheDocument();
    expect(screen.queryByText(/passkeys we accept/i)).toBeNull();
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('saves both limits through the passkey step-up, an empty field as the platform default', async () => {
    const sent = server((count, body) => (count === 1 ? stepUpRequired : { status: 200, data: { ...policy, ...(body as object) } }));
    let prompted = 0;
    setStepUpHandler(() => {
      prompted += 1;
      return Promise.resolve(true);
    });
    await renderScreen();
    fireEvent.change(screen.getByLabelText(IDLE), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText(ABSOLUTE), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Saved. New limits apply to sessions from their next refresh.')).toBeInTheDocument();
    expect(prompted).toBe(1);
    expect(puts(sent)).toEqual([
      { sessionIdleMinutes: null, sessionAbsoluteHours: 10 },
      { sessionIdleMinutes: null, sessionAbsoluteHours: 10 },
    ]);
  });

  it('says nothing was saved when the passkey is not confirmed', async () => {
    server(() => stepUpRequired);
    setStepUpHandler(() => Promise.resolve(false));
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Nothing was saved. Saving needs your passkey.')).toBeInTheDocument();
    expect(screen.queryByText(/^Saved\./)).toBeNull();
  });

  it('renders the 422 above_platform_maximum under the field it names, by its code', async () => {
    server(() => ({
      status: 422,
      data: { code: 'above_platform_maximum', detail: 'server words', errors: [{ field: 'sessionAbsoluteHours', message: 'server words' }] },
    }));
    await renderScreen();
    fireEvent.change(screen.getByLabelText(ABSOLUTE), { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const error = await screen.findByText('At most 24 hours. Choose 24 or fewer.');
    expect(error).toHaveAttribute('id', 'security-absolute-error');
    expect(screen.getByLabelText(ABSOLUTE)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(IDLE)).not.toHaveAttribute('aria-invalid');
    expect(screen.queryByText('server words')).toBeNull();
  });

  it('refuses anything but a whole number of at least 1 before sending, and Cancel restores the limits in force', async () => {
    const sent = server();
    await renderScreen();
    fireEvent.change(screen.getByLabelText(IDLE), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Enter a whole number of at least 1, or leave it empty.')).toBeInTheDocument();
    expect(puts(sent)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByLabelText(IDLE)).toHaveValue('30');
    expect(screen.queryByText('Enter a whole number of at least 1, or leave it empty.')).toBeNull();
  });

  it('offers a retry when the policy cannot be read', async () => {
    installAdapter((sent) => (sent.path === REFRESH_PATH ? { status: 200, data: { accessToken: 'tok' } } : { status: 500, data: { code: 'server_error', detail: '' } }));
    const { wrapper: Query } = queryWrapper();
    render(
      <Query>
        <SecurityPolicyScreen />
      </Query>,
    );
    expect(await screen.findByText('Could not load the security policy')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled());
  });
});
