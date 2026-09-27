import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import OutOfOfficePage from '@/app/(tenant)/me/out-of-office/page';
import type { Me } from '@/features/identity/types';
import { findDestination } from '@/shared/navigation/registry';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';
import { defaultFormatContext, formatLongDate } from '@/shared/utils/format';

import type { OutOfOffice } from './api';
import { outOfOfficeKeys } from './hooks';
import { todayIn } from './OutOfOfficeScreen';

// Out of office (design/screens/me-out-of-office.html): the last day away on
// the bank's calendar, the delegate picked from the bank's people, End now,
// and each refusal from its code: already_delegated as the form's alert with
// Show it, delegate_cannot_approve and a validation error under their field.

const ME_PATH = '/api/v1/me';
const OOO_PATH = '/api/v1/me/out-of-office';
const PEOPLE_PATH = '/api/v1/reference/people';
// Far from the device's zone, so a day taken from the device would show.
const TZ = 'Pacific/Kiritimati';

const SELF = { id: 'u1', name: 'Henrik Wallin' };
const ERIK = { id: 'u2', name: 'Erik Holm' };
const ERIKA = { id: 'u3', name: 'Erika Ström' };
const NOT_AWAY: OutOfOffice = { untilDate: null, delegate: null, away: false };

function me(): Me {
  return {
    user: { id: SELF.id, email: 'away@example.test', name: SELF.name, locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: TZ },
    roles: [],
    permissions: [],
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 1,
    stepUpValidUntil: null,
    counts: { triage: 0, proposals: 0, assignedToMe: 0, unreadNotifications: 0, signoffs: 0, riskAcceptances: 0, supportAccessRequests: 0, tenantReachRequests: 0 },
    lastVisitAt: null,
    notificationPrefs: null,
    headOf: [],
  };
}

interface Script {
  start?: OutOfOffice;
  get?: Answer;
  put?: Answer;
  people?: Answer;
}

/** GET answers the stored absence; PUT stores what it is sent, or answers `put` once. */
function server(script: Script = {}): Sent[] {
  let stored = script.start ?? NOT_AWAY;
  let refusal = script.put;
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: me() };
    if (sent.path === PEOPLE_PATH) return script.people ?? { status: 200, data: [ERIK, ERIKA, SELF] };
    if (sent.path === OOO_PATH && sent.method === 'get') return script.get ?? { status: 200, data: stored };
    if (sent.path === OOO_PATH && sent.method === 'put') {
      if (refusal !== undefined) {
        const answer = refusal;
        refusal = undefined;
        return answer;
      }
      const body = sent.body as { untilDate: string | null; delegateId: string | null };
      const delegate = [ERIK, ERIKA].find((p) => p.id === body.delegateId) ?? null;
      stored = { untilDate: body.untilDate, delegate, away: body.untilDate !== null };
      return { status: 200, data: stored };
    }
    return { status: 404, data: { code: 'not_found', detail: 'Not in this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const puts = (sent: Sent[]) => sent.filter((s) => s.method === 'put').map((s) => s.body);
const until = () => screen.getByLabelText('Away until');
const delegate = () => screen.getByRole('combobox', { name: 'Delegate' });

async function fillForm(day: string, name: string) {
  fireEvent.change(await screen.findByLabelText('Away until'), { target: { value: day } });
  fireEvent.change(delegate(), { target: { value: name.slice(0, 3) } });
  fireEvent.mouseDown(within(screen.getByRole('listbox', { name: 'People' })).getByRole('option', { name }));
}

describe('todayIn', () => {
  it('is the calendar day in the given zone, not the device’s', () => {
    const instant = new Date('2026-09-25T22:30:00Z');
    expect(todayIn('Europe/Stockholm', instant)).toBe('2026-09-26');
    expect(todayIn('America/New_York', instant)).toBe('2026-09-25');
  });
});

describe('out of office', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('is an account destination any member reaches', () => {
    expect(findDestination('me-out-of-office')).toMatchObject({ href: '/me/out-of-office', anyOfPermissions: [], parent: 'account' });
  });

  it('asks for the last day in the bank timezone, from the bank’s today, and a delegate other than yourself', async () => {
    server();
    renderIn(<OutOfOfficePage />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Out of office' })).toBeInTheDocument();
    await waitFor(() => expect(until()).toHaveAttribute('min', todayIn(TZ)));
    expect(screen.getByText(`Your last day away, in your organisation's timezone (${TZ}). Everything comes back to you the day after.`)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set out of office' })).toBeDisabled();

    fireEvent.focus(delegate());
    const options = within(await screen.findByRole('listbox', { name: 'People' })).getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual([ERIK.name, ERIKA.name]);
    fireEvent.change(delegate(), { target: { value: 'zz' } });
    expect(screen.getByText('No one in your organisation matches "zz".')).toBeInTheDocument();
  });

  it('sets the absence with the chosen day and delegate, then shows it with End now', async () => {
    const sent = server();
    renderIn(<OutOfOfficePage />);
    const day = todayIn(TZ);
    await fillForm(day, ERIK.name);
    expect(delegate()).toHaveValue(ERIK.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    expect(await screen.findByRole('heading', { name: 'You are away' })).toBeInTheDocument();
    expect(puts(sent)).toEqual([{ untilDate: day, delegateId: ERIK.id }]);
    expect(screen.getByText(new RegExp(`Erik Holm receives your approval requests and reminders\\.`))).toBeInTheDocument();
  });

  it('ends the absence early with both fields empty and says you are back', async () => {
    const sent = server({ start: { untilDate: '2026-10-02', delegate: ERIK, away: true } });
    renderIn(<OutOfOfficePage />);
    const date = formatLongDate('2026-10-02', { ...defaultFormatContext, timeZone: TZ });
    expect(await screen.findByText(`Until ${date}. Erik Holm receives your approval requests and reminders.`)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'End now' }));
    expect(await screen.findByText('You are back. Approval requests and reminders come to you again.')).toBeInTheDocument();
    expect(puts(sent)).toEqual([{ untilDate: null, delegateId: null }]);
    expect(screen.getByRole('button', { name: 'Set out of office' })).toBeInTheDocument();
  });

  it('says so from already_delegated, and Show it reads the absence set meanwhile', async () => {
    server({ put: { status: 409, data: { code: 'already_delegated', detail: 'Server words.' } } });
    renderIn(<OutOfOfficePage />);
    await fillForm(todayIn(TZ), ERIK.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('You are already away. End that first to set a new one.');
    expect(screen.queryByText('Server words.')).toBeNull();
    // Meanwhile another device set one: Show it reads it back.
    server({ start: { untilDate: '2026-10-02', delegate: ERIK, away: true } });
    fireEvent.click(screen.getByRole('button', { name: 'Show it' }));
    expect(await screen.findByRole('heading', { name: 'You are away' })).toBeInTheDocument();
  });

  it('puts delegate_cannot_approve under the delegate, naming them', async () => {
    server({ put: { status: 422, data: { code: 'delegate_cannot_approve', detail: 'x', errors: [{ field: 'delegateId', message: 'x' }] } } });
    renderIn(<OutOfOfficePage />);
    await fillForm(todayIn(TZ), ERIKA.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    const error = await screen.findByText('Erika Ström cannot approve, so they cannot stand in for you. Choose someone whose role can approve.');
    expect(error).toHaveAttribute('id', 'ooo-delegate-error');
    expect(delegate()).toHaveAttribute('aria-invalid', 'true');
    expect(delegate()).toHaveAttribute('aria-describedby', 'ooo-delegate-error');
  });

  it('puts a validation error under the field it names', async () => {
    server({ put: { status: 422, data: { code: 'validation_error', detail: 'x', errors: [{ field: 'untilDate', message: 'x' }] } } });
    renderIn(<OutOfOfficePage />);
    await fillForm(todayIn(TZ), ERIK.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    expect(await screen.findByText('Choose today or a later date.')).toHaveAttribute('id', 'ooo-until-error');
    expect(until()).toHaveAttribute('aria-invalid', 'true');
  });

  it('shows the error with Try again when the absence cannot be read', async () => {
    server({ get: { status: 503, data: { code: 'unavailable', detail: 'Down.' } } });
    renderIn(<OutOfOfficePage />);
    expect(await screen.findByText('Could not load your out of office')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('moves through the people with the arrow keys, wrapping, and Enter chooses', async () => {
    server();
    renderIn(<OutOfOfficePage />);
    fireEvent.change(await screen.findByLabelText('Away until'), { target: { value: todayIn(TZ) } });
    const input = delegate();
    // Enter while the list is closed chooses nothing.
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(input).toHaveValue('');
    expect(input).toHaveAttribute('aria-expanded', 'false');
    expect(input).not.toHaveAttribute('aria-activedescendant');

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    const listbox = await screen.findByRole('listbox', { name: 'People' });
    const selected = () => within(listbox).getByRole('option', { selected: true });
    expect(selected()).toHaveTextContent(ERIKA.name);
    expect(input).toHaveAttribute('aria-activedescendant', selected().id);
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(selected()).toHaveTextContent(ERIK.name);
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(selected()).toHaveTextContent(ERIKA.name);

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(input).toHaveValue(ERIKA.name);
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(screen.getByRole('button', { name: 'Set out of office' })).toBeEnabled();

    // Typing again drops the choice, so the form cannot be sent until someone is chosen.
    fireEvent.change(input, { target: { value: 'Erik' } });
    expect(screen.getByRole('button', { name: 'Set out of office' })).toBeDisabled();
    expect(screen.getByRole('listbox', { name: 'People' })).toBeInTheDocument();
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    fireEvent.focus(input);
    expect(screen.getByRole('listbox', { name: 'People' })).toBeInTheDocument();
    fireEvent.blur(input);
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('keeps the arrow keys on nothing when no one matches, and Enter chooses no one', async () => {
    server();
    renderIn(<OutOfOfficePage />);
    await screen.findByLabelText('Away until');
    fireEvent.change(delegate(), { target: { value: 'zz' } });
    fireEvent.keyDown(delegate(), { key: 'ArrowDown' });
    fireEvent.keyDown(delegate(), { key: 'Enter' });
    expect(screen.getByText('No one in your organisation matches "zz".')).toBeInTheDocument();
    expect(delegate()).toHaveValue('zz');
    expect(delegate()).not.toHaveAttribute('aria-activedescendant');
    // Other keys leave the list as it is.
    fireEvent.keyDown(delegate(), { key: 'a' });
    expect(screen.getByRole('status')).toHaveTextContent('No one in your organisation matches "zz".');
  });

  it('puts a validation error naming the delegate under the delegate, skipping entries that name nothing', async () => {
    server({ put: { status: 422, data: { code: 'validation_error', detail: 'x', errors: ['untilDate', null, { message: 'x' }, { field: 'delegateId', message: 'x' }] } } });
    renderIn(<OutOfOfficePage />);
    await fillForm(todayIn(TZ), ERIK.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    expect(await screen.findByText('Choose another active member of your organisation.')).toHaveAttribute('id', 'ooo-delegate-error');
    expect(until()).toHaveAttribute('aria-invalid', 'false');
    // The field's error is the only alert: no form-level alert as well.
    expect(screen.getAllByRole('alert')).toHaveLength(1);
  });

  it('shows a validation error that names no field of the form as the form’s alert', async () => {
    server({ put: { status: 422, data: { code: 'validation_error', detail: 'The request was not valid.', errors: [{ field: 'other', message: 'x' }] } } });
    renderIn(<OutOfOfficePage />);
    await fillForm(todayIn(TZ), ERIK.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The request was not valid.');
    expect(until()).toHaveAttribute('aria-invalid', 'false');
    expect(delegate()).toHaveAttribute('aria-invalid', 'false');
  });

  it('shows any other refusal as the form’s alert, by its code', async () => {
    server({ put: { status: 503, data: { code: 'unavailable', detail: 'Try later.' } } });
    renderIn(<OutOfOfficePage />);
    await fillForm(todayIn(TZ), ERIK.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    expect(await screen.findByRole('alert')).toHaveAttribute('data-problem-code', 'unavailable');
    expect(screen.queryByRole('button', { name: 'Show it' })).toBeNull();
  });

  it('shows why the people cannot be read in place of the delegate', async () => {
    server({ people: { status: 503, data: { code: 'unavailable', detail: 'People are down.' } } });
    renderIn(<OutOfOfficePage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('People are down.');
    expect(screen.queryByRole('combobox', { name: 'Delegate' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Set out of office' })).toBeDisabled();
  });

  it('keeps you away and says why when End now is refused', async () => {
    server({ start: { untilDate: '2026-10-02', delegate: ERIK, away: true }, put: { status: 503, data: { code: 'unavailable', detail: 'Could not end it.' } } });
    renderIn(<OutOfOfficePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'End now' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not end it.');
    expect(screen.getByRole('heading', { name: 'You are away' })).toBeInTheDocument();
    expect(screen.queryByText('You are back. Approval requests and reminders come to you again.')).toBeNull();
  });

  it('reads the absence again from Try again', async () => {
    const sent = server({ get: { status: 503, data: { code: 'unavailable', detail: 'Down.' } } });
    renderIn(<OutOfOfficePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(sent.filter((s) => s.path === OOO_PATH && s.method === 'get')).toHaveLength(2));
  });

  it('sends nothing when the form is submitted without a day or a delegate', async () => {
    const sent = server();
    renderIn(<OutOfOfficePage />);
    const form = (await screen.findByLabelText('Away until')).closest('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);
    fireEvent.change(until(), { target: { value: todayIn(TZ) } });
    fireEvent.submit(form as HTMLFormElement);
    expect(puts(sent)).toEqual([]);
  });

  it('shows a validation error without field entries as the form’s alert', async () => {
    server({ put: { status: 422, data: { code: 'validation_error', detail: 'Not valid.' } } });
    renderIn(<OutOfOfficePage />);
    await fillForm(todayIn(TZ), ERIK.name);
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    expect(await screen.findByRole('alert')).toHaveAttribute('data-problem-code', 'validation_error');
    expect(until()).toHaveAttribute('aria-invalid', 'false');
  });

  it('still keeps delegate_cannot_approve under the delegate when they left the people list meanwhile', async () => {
    let people = [ERIK, ERIKA, SELF];
    installAdapter((sent) => {
      if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
      if (sent.path === ME_PATH) return { status: 200, data: me() };
      if (sent.path === PEOPLE_PATH) return { status: 200, data: people };
      if (sent.path === OOO_PATH && sent.method === 'get') return { status: 200, data: NOT_AWAY };
      return { status: 422, data: { code: 'delegate_cannot_approve', detail: 'x' } };
    });
    const { wrapper: Query, queryClient } = queryWrapper();
    render(
      <Query>
        <OutOfOfficePage />
      </Query>,
    );
    await fillForm(todayIn(TZ), ERIKA.name);
    people = [ERIK, SELF];
    await act(() => queryClient.refetchQueries({ queryKey: outOfOfficeKeys.people }));
    fireEvent.click(screen.getByRole('button', { name: 'Set out of office' }));
    const error = await screen.findByText(/cannot approve, so they cannot stand in for you\./);
    expect(error).toHaveAttribute('id', 'ooo-delegate-error');
    expect(error.textContent?.startsWith(' cannot approve')).toBe(true);
  });
});
