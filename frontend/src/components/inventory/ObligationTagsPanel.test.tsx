import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { libraryKeys } from '@/features/library/hooks';
import type { ObligationDetail } from '@/features/library/types';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ObligationTagsPanel } from './ObligationTagsPanel';

// "Our tags" on the obligation card (VOC-03, VOC-08, VOC-S6): the bank's tags
// from the obligation read, removed and added by a holder of vocab.manage
// through the tagging routes, read only for everyone else, whose picker offers
// only Suggest. The server's refusals render under the tags.

const ID = '11111111-1111-4111-8111-111111111111';
const custody = { key: 'custody', kind: null, label: 'Custody' };

const rows = [
  { key: 'custody', kind: null, label: 'Custody', labels: { en: 'Custody' }, usageNote: '', sortOrder: 1, active: true, isSystem: false, isDefault: false, usageCount: 4, extra: {} },
  { key: 'onboarding', kind: null, label: 'Onboarding', labels: { en: 'Onboarding' }, usageNote: '', sortOrder: 2, active: true, isSystem: false, isDefault: false, usageCount: 2, extra: {} },
];

function renderPanel(permissions: string[], tenantTags: ObligationDetail['tenantTags'], script: (sent: Sent) => Answer | undefined = () => undefined) {
  const sent = installAdapter((s) => script(s) ?? (s.method === 'get' && s.path.includes('/vocab/tenant_tag') ? { status: 200, data: rows } : { status: 500 }));
  const { wrapper, queryClient } = queryWrapper();
  // The screen has already read the obligation; the panel reads the same answer.
  queryClient.setQueryDefaults(libraryKeys.obligation(ID, ''), { staleTime: Infinity, gcTime: Infinity });
  queryClient.setQueryData(libraryKeys.obligation(ID, ''), { id: ID, tenantTags } as unknown as ObligationDetail);
  render(createElement(PermissionsProvider, { permissions, children: createElement(ObligationTagsPanel, { obligationId: ID }) }), {
    wrapper: wrapper as (p: { children: ReactNode }) => ReactNode,
  });
  return sent;
}

async function typeInPicker(text: string) {
  const input = await screen.findByRole('combobox');
  await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
  fireEvent.change(input, { target: { value: text } });
  return input;
}

describe('ObligationTagsPanel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('removes a tag for a holder of vocab.manage through the tagging route and shows the tags that remain', async () => {
    const sent = renderPanel(['vocab.manage'], [custody], (s) =>
      s.method === 'post' ? { status: 200, data: { subjectType: 'obligation', subjectId: ID, tags: [] } } : undefined,
    );
    expect(screen.getByText('Custody')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Remove Custody' }));
    await screen.findByText('None yet');
    const write = sent.find((s) => s.method === 'post');
    expect(write?.path).toBe('/api/v1/taggings/remove');
    expect(write?.body).toEqual({ tagKey: 'custody', subjectType: 'obligation', subjectId: ID });
  });

  it('adds an existing tag with the picker, the existing tag first and Create last', async () => {
    const sent = renderPanel(['vocab.manage'], [], (s) =>
      s.method === 'post' ? { status: 200, data: { subjectType: 'obligation', subjectId: ID, tags: [{ key: 'onboarding', kind: null, label: 'Onboarding' }] } } : undefined,
    );
    expect(screen.getByText('None yet')).toBeTruthy();
    const input = await typeInPicker('onb');
    const options = screen.getAllByRole('option');
    expect(options[0]?.getAttribute('data-picker-option')).toBe('onboarding');
    expect(options.at(-1)?.getAttribute('data-picker-last')).toBe('create');
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(document.querySelector('[data-obligation-tag="onboarding"]')).not.toBeNull());
    const write = sent.find((s) => s.method === 'post');
    expect(write?.path).toBe('/api/v1/taggings');
    expect(write?.body).toEqual({ tagKey: 'onboarding', subjectType: 'obligation', subjectId: ID });
  });

  it('never offers a tag the obligation already carries', async () => {
    renderPanel(['vocab.manage'], [custody]);
    await typeInPicker('cust');
    expect(document.querySelector('[data-picker-option="custody"]')).toBeNull();
  });

  it('is read only without vocab.manage: no remove, no pick, and the picker offers Suggest', async () => {
    const sent = renderPanel([], [custody]);
    expect(screen.getByText('Custody')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Remove Custody' })).toBeNull();
    expect(screen.getByLabelText('Suggest a tag')).toBeTruthy();

    const input = await typeInPicker('onb');
    const existing = document.querySelector('[data-picker-option="onboarding"]');
    expect(existing?.getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(existing as Element);
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(sent.filter((s) => s.method === 'post')).toEqual([]);

    await typeInPicker('Pension transfers');
    expect(document.querySelector('[data-picker-last]')?.getAttribute('data-picker-last')).toBe('suggest');
  });

  it('says a tag was retired while the person was choosing, and changes nothing', async () => {
    renderPanel(['vocab.manage'], [], (s) =>
      s.method === 'post' ? { status: 422, data: { status: 422, title: 'Unknown key', detail: 'x', code: 'unknown_key' } } : undefined,
    );
    const input = await typeInPicker('onb');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect((await screen.findByRole('alert')).textContent).toBe('"Onboarding" was retired while you were choosing. Pick another tag.');
    expect(screen.getByText('None yet')).toBeTruthy();
  });

  it('says the roles no longer include managing vocabularies on a 403', async () => {
    renderPanel(['vocab.manage'], [custody], (s) =>
      s.method === 'post' ? { status: 403, data: { status: 403, title: 'Forbidden', detail: 'x', code: 'permission_denied' } } : undefined,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Remove Custody' }));
    expect((await screen.findByRole('alert')).textContent).toBe('Your roles no longer include managing vocabularies. The tags are as they were.');
    expect(screen.getByText('Custody')).toBeTruthy();
  });

  it('offers Try again after a failure, which sends the same change', async () => {
    let calls = 0;
    const sent = renderPanel(['vocab.manage'], [custody], (s) => {
      if (s.method !== 'post') return undefined;
      calls += 1;
      return calls === 1 ? { status: 500, data: { status: 500, title: 'Error', detail: '', code: 'internal' } } : { status: 200, data: { subjectType: 'obligation', subjectId: ID, tags: [] } };
    });
    fireEvent.click(screen.getByRole('button', { name: 'Remove Custody' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Could not change the tags.');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByText('None yet');
    expect(sent.filter((s) => s.method === 'post').map((s) => s.path)).toEqual(['/api/v1/taggings/remove', '/api/v1/taggings/remove']);
  });
});
