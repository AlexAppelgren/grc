import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ObligationLinksPanel } from './ObligationLinksPanel';

// "Linked internal items" (REG-05): the list with kind and reference, a
// reader's view without controls, the dialog that picks or creates in one
// call, a refusal read by its code, and a removal that confirms first.

const EDITOR = ['register.read', 'register.edit', 'library.read'];
const READER = ['register.read', 'library.read'];
const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };

const policy = {
  id: 'l-1',
  kind: { key: 'policy', kind: null, label: 'Policy' },
  label: 'Research and inducements policy',
  url: 'https://intranet.example-bank.test/pol-014',
  externalRef: 'POL-014',
  externalSystem: null,
  internalItemId: 'i-1',
  createdBy: SARA,
  createdAt: '2026-09-18T09:00:00Z',
};
const control = { ...policy, id: 'l-2', kind: { key: 'control', kind: null, label: 'Control' }, label: 'Yearly value test', url: 'javascript:alert(1)', externalRef: null };
const reconciliation = { id: 'i-9', kind: { key: 'control', kind: null, label: 'Control' }, name: 'Daily reconciliation', reference: 'CTL-203' };

function serve(links: unknown[], write: (sent: Sent) => Answer = () => ({ status: 201, data: policy })) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u-sara', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: EDITOR, enrolmentPending: false } };
    if (sent.path === '/api/v1/internal-items') return { status: 200, data: { items: [reconciliation], total: 1 } };
    if (sent.path === '/api/v1/vocab/link_kind') return { status: 200, data: { items: [{ key: 'policy', kind: null, label: 'Policy', labels: {}, usageNote: '', sortOrder: 1, active: true }, { key: 'control', kind: null, label: 'Control', labels: {}, usageNote: '', sortOrder: 2, active: true }], total: 2 } };
    if (sent.method === 'get') return { status: 200, data: { items: links, total: links.length } };
    return write(sent);
  });
}

function renderPanel(permissions: string[]) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <ObligationLinksPanel obligationId="ob-1" />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

describe('ObligationLinksPanel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('lists each link with its kind label and reference, opens only a web address, and offers a reader no control', async () => {
    serve([policy, control]);
    renderPanel(READER);
    const first = await screen.findByText('Research and inducements policy');
    expect(first.closest('a')?.getAttribute('href')).toBe('https://intranet.example-bank.test/pol-014');
    expect(screen.getByText('Yearly value test').closest('a')).toBeNull();
    const row = document.querySelector<HTMLElement>('[data-link-id="l-1"]');
    expect(within(row as HTMLElement).getByText('Policy')).toBeTruthy();
    expect(within(row as HTMLElement).getByText('POL-014')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Link an item' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
  });

  it('says so when nothing is linked', async () => {
    serve([]);
    renderPanel(EDITOR);
    expect(await screen.findByText(/Nothing linked yet/)).toBeTruthy();
  });

  it('picks one of the bank’s items and links it in one call', async () => {
    const sent = serve([]);
    renderPanel(EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Link an item' }));
    fireEvent.change(screen.getByRole('searchbox', { name: 'Find an item' }), { target: { value: 'reconc' } });
    fireEvent.click(await screen.findByRole('radio', { name: /Daily reconciliation/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    await waitFor(() => expect(sent.some((s) => s.method === 'post')).toBe(true));
    const post = sent.find((s) => s.method === 'post');
    expect(post?.path).toBe('/api/v1/obligations/ob-1/internal-links');
    expect(post?.body).toEqual({ kind: 'control', label: 'Daily reconciliation', internalItemId: 'i-9', externalRef: 'CTL-203' });
    expect(sent.filter((s) => s.path === '/api/v1/internal-items').map((s) => s.params)).toContainEqual({ q: 'reconc' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('creates an item from the dialog and shows a refusal from its code', async () => {
    const sent = serve([], () => ({ status: 409, data: { code: 'duplicate_key', detail: 'server words' } }));
    renderPanel(EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Link an item' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create a new item instead' }));
    await screen.findByRole('option', { name: 'Control' });
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'control' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Daily reconciliation' } });
    fireEvent.change(screen.getByLabelText('Your reference'), { target: { value: 'CTL-203' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create and link' }));
    expect(await screen.findByText('An item of this kind with this name already exists. Pick it instead.')).toBeTruthy();
    expect(sent.find((s) => s.method === 'post')?.body).toEqual({ kind: 'control', label: 'Daily reconciliation', reference: 'CTL-203', externalRef: 'CTL-203', url: null });
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('searchbox', { name: 'Find an item' })).toBeTruthy();
  });

  it('says an item is already linked, by its code', async () => {
    serve([], () => ({ status: 409, data: { code: 'already_linked', detail: 'server words' } }));
    renderPanel(EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Link an item' }));
    fireEvent.click(await screen.findByRole('radio', { name: /Daily reconciliation/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    expect(await screen.findByText('That item is already linked to this obligation.')).toBeTruthy();
  });

  it('removes a link only after the confirmation', async () => {
    const sent = serve([policy], () => ({ status: 204 }));
    renderPanel(EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
    const dialog = screen.getByRole('dialog', { name: 'Remove the link to "Research and inducements policy"?' });
    expect(within(dialog).getByText('The item itself stays, with its other links.')).toBeTruthy();
    expect(sent.some((s) => s.method === 'delete')).toBe(false);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove link' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'delete')?.path).toBe('/api/v1/internal-links/l-1'));
  });
});
