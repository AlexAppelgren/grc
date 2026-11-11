import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { MembersScreen } from '@/components/admin/MembersScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';

// Inviting a person (ID-01): an invitation grants roles, so the server asks
// for a passkey step-up as it does for a role change (review 2026-11-11 S-4).
// The api client opens the prompt on step_up_required and sends once more;
// a cancelled prompt leaves the form saying nothing changed.

const MEMBERS = '/api/v1/tenant/members';
const reader = { key: 'reader', kind: 'system', label: 'Reader', active: true, usageNote: '', isSystem: true, permissions: [], memberCount: 0 };
const invitation = { id: 'i1', email: 'new.analyst@example-bank.test', roles: [{ key: 'reader', kind: 'system', label: 'Reader' }], title: '', kind: 'invite', status: 'pending', createdAt: '2026-11-11T08:00:00Z', expiresAt: '2026-11-14T08:00:00Z' };
const stepUpRequired: Answer = { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.', status: 403 } };

function server(invite: (count: number) => Answer): Sent[] {
  let posts = 0;
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === MEMBERS && sent.method === 'post') {
      posts += 1;
      return invite(posts);
    }
    if (sent.path === MEMBERS) return { status: 200, data: { items: [], total: 0 } };
    if (sent.path === '/api/v1/tenant/invitations') return { status: 200, data: { items: [], total: 0 } };
    if (sent.path === '/api/v1/tenant/roles') return { status: 200, data: [reader] };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

async function invite(): Promise<HTMLElement> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <MembersScreen />
    </Query>,
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Invite a person' }));
  const form = await screen.findByRole('dialog', { name: 'Invite a person' });
  fireEvent.change(within(form).getByLabelText('Email address'), { target: { value: 'new.analyst@example-bank.test' } });
  fireEvent.click(await within(form).findByLabelText('Reader'));
  fireEvent.click(within(form).getByRole('button', { name: 'Send invitation' }));
  return form;
}

beforeEach(() => {
  resetApiForTests();
});

describe('inviting a person', () => {
  it('opens the passkey prompt when the server asks for one, and sends the invitation once it is confirmed', async () => {
    let prompts = 0;
    setStepUpHandler(() => {
      prompts += 1;
      return Promise.resolve(true);
    });
    const sent = server((count) => (count === 1 ? stepUpRequired : { status: 201, data: invitation }));
    await invite();
    expect(await screen.findByText('Invitation sent to new.analyst@example-bank.test.')).toBeInTheDocument();
    expect(prompts).toBe(1);
    expect(sent.filter((s) => s.method === 'post' && s.path === MEMBERS).map((s) => s.body)).toEqual([
      { email: 'new.analyst@example-bank.test', roleKeys: ['reader'], title: '' },
      { email: 'new.analyst@example-bank.test', roleKeys: ['reader'], title: '' },
    ]);
  });

  it('says nothing changed when the passkey prompt is cancelled', async () => {
    setStepUpHandler(() => Promise.resolve(false));
    server(() => stepUpRequired);
    const form = await invite();
    expect(await within(form).findByText('The action was not confirmed, so nothing changed.')).toBeInTheDocument();
  });
});
