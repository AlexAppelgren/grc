import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { Me } from '@/features/identity/types';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { api, pathOf, REFRESH_PATH } from '@/shared/utils/api-client';

import { NotificationPreferences } from './NotificationPreferences';
import type { NotificationPrefs } from './types';

// "What reaches you" (design/screens/tenant-notifications.html, blocks 10 and
// 11): one switch per kind a person may turn off, the weekly briefing among
// them, escalations held on with a line why, each change saved at once as the
// whole set of switches, moved before the answer and put back on a refusal.

const ME_PATH = '/api/v1/me';
const ALL_ON: NotificationPrefs = { mentions: true, assignments: true, reminders: true, weeklyDigest: true, weeklyBriefing: true };

function me(notificationPrefs: NotificationPrefs | null): Me {
  return {
    user: { id: 'u1', email: 'sara@example.test', name: 'Sara Lindqvist', locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
    roles: [],
    permissions: [],
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 1,
    stepUpValidUntil: null,
    counts: { triage: 0, proposals: 0, assignedToMe: 0, unreadNotifications: 0 },
    lastVisitAt: null,
    notificationPrefs,
    headOf: [],
  };
}

/** GET /me answers the stored switches; PATCH /me stores what it is sent, or answers `patch`. */
function server(start: NotificationPrefs | null, patch?: Answer): Sent[] {
  let stored = start;
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH && sent.method === 'get') return { status: 200, data: me(stored) };
    if (sent.path === ME_PATH && sent.method === 'patch') {
      if (patch !== undefined) return patch;
      stored = (sent.body as { notificationPrefs: NotificationPrefs }).notificationPrefs;
      return { status: 200, data: me(stored) };
    }
    return { status: 404, data: { code: 'not_found', detail: 'Not in this test.' } };
  });
}

function hold(path: string): () => void {
  const inner = api.defaults.adapter as AxiosAdapter;
  let release = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  api.defaults.adapter = async (config) => {
    if (pathOf(config) === path && config.method === 'patch') await gate;
    return inner(config);
  };
  return release;
}

/** A PATCH that never reaches the server: no response at all. */
function offline(): void {
  const inner = api.defaults.adapter as AxiosAdapter;
  api.defaults.adapter = async (config) => {
    if (config.method === 'patch') throw new AxiosError('Network Error', 'ERR_NETWORK', config as InternalAxiosRequestConfig);
    return inner(config);
  };
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const switchOf = (name: string) => screen.getByRole('switch', { name });
const patches = (sent: Sent[]) => sent.filter((s) => s.method === 'patch').map((s) => s.body);

describe('notification preferences', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('shows one switch per kind a person may turn off, the weekly briefing included, and escalations held on with why', async () => {
    server({ ...ALL_ON, reminders: false });
    renderIn(<NotificationPreferences />);
    expect(await screen.findByRole('heading', { name: 'What reaches you' })).toBeInTheDocument();
    const names = screen.getAllByRole('switch').map((s) => s.getAttribute('aria-labelledby'));
    expect(names).toEqual(['pref-mentions', 'pref-assignments', 'pref-reminders', 'pref-weeklyDigest', 'pref-weeklyBriefing']);
    expect(switchOf('Weekly briefing')).toHaveAttribute('aria-checked', 'true');
    expect(switchOf('Reminders')).toHaveAttribute('aria-checked', 'false');
    // Escalations are the bank's: no switch, the held glyph and the line why.
    expect(screen.queryByRole('switch', { name: 'Escalations' })).toBeNull();
    const held = document.querySelector('[data-pref-held="escalation"]') as HTMLElement;
    expect(held).toHaveTextContent('Always on');
    expect(screen.getByText(/Your organisation decides these, so they always reach you\./)).toBeInTheDocument();
  });

  it('saves a change at once as the whole set of switches, moving the switch before the answer', async () => {
    const sent = server(ALL_ON);
    renderIn(<NotificationPreferences />);
    await screen.findByRole('switch', { name: 'Weekly briefing' });
    const release = hold(ME_PATH);
    fireEvent.click(switchOf('Weekly briefing'));
    await waitFor(() => expect(switchOf('Weekly briefing')).toHaveAttribute('aria-checked', 'false'));
    expect(screen.getByRole('status')).toHaveTextContent('Saving…');
    expect(switchOf('Mentions')).toBeDisabled();
    release();
    expect(await screen.findByText('Saved.')).toBeInTheDocument();
    expect(patches(sent)).toEqual([{ notificationPrefs: { ...ALL_ON, weeklyBriefing: false } }]);
    expect(switchOf('Weekly briefing')).toHaveAttribute('aria-checked', 'false');
  });

  it('puts the switch back and says so when the save does not reach the server', async () => {
    server(ALL_ON);
    renderIn(<NotificationPreferences />);
    await screen.findByRole('switch', { name: 'Mentions' });
    offline();
    fireEvent.click(switchOf('Mentions'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save. The switch is back where it was. Check your connection and try again.');
    expect(switchOf('Mentions')).toHaveAttribute('aria-checked', 'true');
  });

  it('puts the switch back and shows the server refusal by its code', async () => {
    server(ALL_ON, { status: 422, data: { code: 'unknown_key', detail: 'Unknown notification preference.' } });
    renderIn(<NotificationPreferences />);
    await screen.findByRole('switch', { name: 'Assignments' });
    fireEvent.click(switchOf('Assignments'));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-problem-code', 'unknown_key');
    expect(alert).toHaveTextContent('Unknown notification preference.');
    expect(switchOf('Assignments')).toHaveAttribute('aria-checked', 'true');
  });

  it('renders nothing for a session without a bank', async () => {
    const sent = server(null);
    const { container } = renderIn(<NotificationPreferences />);
    await waitFor(() => expect(sent.some((s) => s.path === ME_PATH)).toBe(true));
    expect(container).toBeEmptyDOMElement();
  });
});
