import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement, useState, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { tokenStore } from '@/shared/utils/api-client';

import { lastOption, VocabularyPicker } from './VocabularyPicker';

// The one picker (design/screens/picker-create-or-suggest.html): Create on a
// tenant list for vocab.manage (VOC-01), Suggest there for everyone else
// (VOC-03), Propose on a library list (VOC-07), the near match first, and the
// server's two refusals in place by their codes (AC-VOC3): 409 duplicate_key
// says the value exists, 422 near_duplicate asks "Did you mean …?".

const rows = [
  { key: 'custody', kind: null, label: 'Custody', labels: { en: 'Custody' }, usageNote: '', sortOrder: 1, active: true, isSystem: false, isDefault: false, usageCount: 4, extra: {} },
  { key: 'onboarding', kind: null, label: 'Onboarding', labels: { en: 'Onboarding' }, usageNote: '', sortOrder: 2, active: true, isSystem: false, isDefault: false, usageCount: 0, extra: {} },
];

function Harness({ list, tier, permissions, initial = [] }: { list: string; tier: 'tenant' | 'library'; permissions: string[]; initial?: string[] }) {
  const [value, setValue] = useState<string[]>(initial);
  return (
    <PermissionsProvider permissions={permissions}>
      <VocabularyPicker list={list} tier={tier} label="Tenant tags" value={value} onChange={setValue} />
      <output data-testid="value">{value.join(',')}</output>
    </PermissionsProvider>
  );
}

function renderPicker(props: Parameters<typeof Harness>[0]) {
  const { wrapper } = queryWrapper();
  return render(createElement(Harness, props), { wrapper: wrapper as (p: { children: ReactNode }) => ReactNode });
}

describe('lastOption', () => {
  it('offers Create on a tenant list with vocab.manage and Suggest without it, and Propose on a library list only with proposals.create', () => {
    expect(lastOption('tenant', ['vocab.manage'])).toBe('create');
    expect(lastOption('tenant', [])).toBe('suggest');
    expect(lastOption('tenant', null)).toBeNull();
    expect(lastOption('library', null)).toBeNull();
    expect(lastOption('library', ['proposals.create'])).toBe('propose');
    expect(lastOption('library', ['vocab.manage'])).toBeNull();
    expect(lastOption('library', [])).toBeNull();
  });
});

describe('VocabularyPicker', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('offers the near match first and picks it', async () => {
    installAdapter(() => ({ status: 200, data: rows }));
    renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: ['vocab.manage'] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'custody svc' } });
    const options = screen.getAllByRole('option');
    expect(options[0]?.getAttribute('data-picker-option')).toBe('custody');
    expect(options[0]?.textContent).toContain('Did you mean this?');
    expect(options.at(-1)?.getAttribute('data-picker-last')).toBe('create');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByTestId('value').textContent).toBe('custody');
  });

  it('suggests on a tenant list without vocab.manage: the suggestion waits for an administrator and is not picked', async () => {
    const sent = installAdapter((s) =>
      s.method === 'get'
        ? { status: 200, data: rows }
        : { status: 201, data: { id: 's1', list: 'tenant_tag', key: 'pension_transfers', labels: { en: 'Pension transfers' }, usageNote: 'Moves', suggestedBy: { id: 'u1', name: 'Johan Berg' }, status: 'pending', createdAt: '2026-09-17T08:00:00Z' } },
    );
    renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: [] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'Pension transfers' } });
    expect(screen.getByText('No value matches')).toBeTruthy();
    expect(screen.getByText('An administrator decides; you will hear back')).toBeTruthy();
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.change(screen.getByLabelText('Usage note'), { target: { value: 'Moves' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send suggestion' }));
    expect(await screen.findByText('Pension transfers, suggested')).toBeTruthy();
    expect(screen.getByText('The suggestion is not on the record until an administrator adds it.')).toBeTruthy();
    expect(document.querySelector('[data-picker-create]')).toBeNull();
    expect(screen.getByTestId('value').textContent).toBe('');
    const post = sent.find((s) => s.method === 'post');
    expect([post?.path, post?.body]).toEqual(['/api/v1/vocab/tenant_tag/suggest', { labels: { en: 'Pension transfers' }, usageNote: 'Moves' }]);
    // Typing again starts over.
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'E' } });
    expect(screen.queryByText('Pension transfers, suggested')).toBeNull();
  });

  it('renders a suggestion refused as the same value (409) or as a near match (422) by its code, with the value to use', async () => {
    let answer: { status: number; data: unknown } = { status: 409, data: { code: 'duplicate_key', detail: 'x', candidates: [{ key: 'custody', label: 'Custody' }] } };
    installAdapter((s) => (s.method === 'get' ? { status: 200, data: rows } : answer));
    renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: [] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'custody x' } });
    fireEvent.click(document.querySelector('[data-picker-last="suggest"]') as Element);
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'custody ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send suggestion' }));
    expect(await screen.findByText('"Custody" already exists.')).toBeTruthy();
    expect(screen.queryByText('Did you mean Custody?')).toBeNull();

    answer = { status: 422, data: { code: 'near_duplicate', detail: 'x', candidates: [{ key: 'custody', label: 'Custody' }] } };
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Custdy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send suggestion' }));
    expect(await screen.findByText('Did you mean Custody?')).toBeTruthy();
    expect(screen.queryByText('"Custody" already exists.')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Use Custody' }));
    expect(screen.getByTestId('value').textContent).toBe('custody');
    expect(document.querySelector('[data-picker-create]')).toBeNull();
  });

  it('creates in place and selects, or renders the near-duplicate refusal with the match', async () => {
    let refuse = true;
    const sent = installAdapter((s) => {
      if (s.method === 'get') return { status: 200, data: rows };
      if (refuse) return { status: 422, data: { code: 'near_duplicate', detail: 'x', candidates: [{ key: 'custody', label: 'Custody' }] } };
      return { status: 201, data: { ...rows[0], key: 'custody_services', label: 'Custody services' } };
    });
    renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: ['vocab.manage'] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'Custody services' } });
    fireEvent.click(screen.getByText('Create "Custody services"'));
    fireEvent.change(screen.getByLabelText('Usage note'), { target: { value: 'Safekeeping' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create and select' }));
    expect(await screen.findByText('Did you mean Custody?')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Use Custody' }));
    expect(screen.getByTestId('value').textContent).toBe('custody');

    refuse = false;
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Custody services' } });
    fireEvent.click(screen.getByText('Create "Custody services"'));
    fireEvent.click(screen.getByRole('button', { name: 'Create and select' }));
    await waitFor(() => expect(screen.getByTestId('value').textContent).toBe('custody,custody_services'));
    expect(sent.find((s) => s.method === 'post')?.body).toEqual({ labels: { en: 'Custody services' }, usageNote: 'Safekeeping' });
  });

  it('proposes a new value on a library list and removes a picked one', async () => {
    const sent = installAdapter((s) => (s.method === 'get' ? { status: 200, data: rows } : { status: 202, data: { proposal: { id: 'p1', kind: 'term_create', status: 'open', title: 'Add "T+1"' } } }));
    renderPicker({ list: 'flag', tier: 'library', permissions: ['proposals.create'], initial: ['custody'] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'T+1' } });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(await screen.findByText('Add "T+1" is waiting for review.')).toBeTruthy();
    expect(sent.find((s) => s.method === 'post')?.path).toBe('/api/v1/vocab/flag/suggest');
    fireEvent.click(screen.getByRole('button', { name: 'Remove Custody' }));
    expect(screen.getByTestId('value').textContent).toBe('');
  });

  it('moves through the options with the arrow keys, closes on Escape, and picks with the mouse', async () => {
    installAdapter(() => ({ status: 200, data: rows }));
    renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: ['vocab.manage'] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'o' } });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(input.getAttribute('aria-activedescendant')).toMatch(/-option-1$/);
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(input.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('listbox')).toBeNull();
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByTestId('value').textContent).toBe('');

    fireEvent.focus(input);
    const onboarding = screen.getAllByRole('option').find((option) => option.getAttribute('data-picker-option') === 'onboarding');
    if (onboarding === undefined) throw new Error('onboarding is not offered');
    fireEvent.mouseDown(onboarding);
    fireEvent.click(onboarding);
    expect(screen.getByTestId('value').textContent).toBe('onboarding');
  });

  it('lets the label be edited before creating, and says why a create failed for any other reason', async () => {
    const sent = installAdapter((s) => (s.method === 'get' ? { status: 200, data: rows } : { status: 500, data: { code: 'server_error', detail: 'Could not save.' } }));
    renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: ['vocab.manage'] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'escrw' } });
    const create = document.querySelector('[data-picker-last="create"]');
    if (create === null) throw new Error('Create is not offered');
    fireEvent.mouseDown(create);
    fireEvent.click(create);
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Escrow' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create and select' }));
    expect(await screen.findByText('Could not save.')).toBeTruthy();
    expect(sent.find((s) => s.method === 'post')?.body).toEqual({ labels: { en: 'Escrow' }, usageNote: '' });
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create and select' }));
    expect(sent.filter((s) => s.method === 'post')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(document.querySelector('[data-picker-create]')).toBeNull();
  });

  it('offers nothing to create or suggest before the permission list is known', async () => {
    installAdapter(() => ({ status: 200, data: rows }));
    const { wrapper } = queryWrapper();
    render(createElement(VocabularyPicker, { list: 'tenant_tag', tier: 'tenant', label: 'Tenant tags', value: [], onChange: () => undefined }), { wrapper: wrapper as (p: { children: ReactNode }) => ReactNode });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'Zzz' } });
    expect(document.querySelector('[data-picker-last]')).toBeNull();
  });

  it('confirms a proposal by what was typed when the answer carries no title, and picks nothing when a create is proposed', async () => {
    let answer: unknown = { proposal: { id: 'p1', kind: 'term_create', status: 'open', title: '' } };
    installAdapter((s) => (s.method === 'get' ? { status: 200, data: rows } : { status: 202, data: answer }));
    renderPicker({ list: 'flag', tier: 'library', permissions: ['proposals.create'] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'Zzz' } });
    fireEvent.click(document.querySelector('[data-picker-last="propose"]') as Element);
    expect(await screen.findByText('Zzz is waiting for review.')).toBeTruthy();

    answer = { proposal: { id: 'p2', kind: 'vocabulary_create', status: 'open', title: 'Add Qqq' } };
    const { unmount } = renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: ['vocab.manage'] });
    const second = (await screen.findAllByRole('combobox')).at(-1) as HTMLInputElement;
    await waitFor(() => expect(second.disabled).toBe(false));
    fireEvent.change(second, { target: { value: 'Qqq' } });
    fireEvent.click(document.querySelectorAll('[data-picker-last="create"]')[0] as Element);
    fireEvent.click(screen.getByRole('button', { name: 'Create and select' }));
    await waitFor(() => expect(document.querySelector('[data-picker-create] [aria-busy]')).toBeNull());
    expect(screen.getAllByTestId('value').at(-1)?.textContent).toBe('');
    unmount();
  });

  it('says why a proposal could not be sent', async () => {
    installAdapter((s) => (s.method === 'get' ? { status: 200, data: rows } : { status: 403, data: { code: 'permission_denied', detail: 'Not allowed.' } }));
    renderPicker({ list: 'flag', tier: 'library', permissions: ['proposals.create'] });
    const input = await screen.findByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: 'Zzz' } });
    const propose = document.querySelector('[data-picker-last="propose"]');
    if (propose === null) throw new Error('Propose is not offered');
    fireEvent.click(propose);
    expect(await screen.findByText(/^Not allowed\./)).toBeTruthy();
  });

  it('says so in place when the values cannot be read', async () => {
    installAdapter(() => ({ status: 500, data: {} }));
    renderPicker({ list: 'tenant_tag', tier: 'tenant', permissions: ['vocab.manage'] });
    expect(await screen.findByText('Could not load the values.')).toBeTruthy();
    // Try again reads the list again, and the picker recovers when it answers.
    installAdapter(() => ({ status: 200, data: rows }));
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('combobox')).toBeTruthy();
  });
});
