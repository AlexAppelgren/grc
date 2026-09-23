import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { OrganisationScreen } from '@/components/admin/OrganisationScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The Organisation profile form (TEN-01, ADM-S17) saves what it says: an
// omitted field is left alone by the server, and an empty list of content
// languages is refused there. So the form sends the languages only when the
// draft changed them, refuses to empty them before sending anything, and
// leaves the default language unset until a person chooses one; a tenant
// created from the console starts with neither (D-68).

const TENANT_PATH = '/api/v1/tenant';
const LANGUAGES_PATH = '/api/v1/reference/languages';

const svenska = { key: 'sv', kind: null, label: 'Svenska' };
const english = { key: 'en', kind: null, label: 'English' };
const suomi = { key: 'fi', kind: null, label: 'Suomi' };

const onboarding = {
  stepsDone: 0,
  steps: ['profile', 'members', 'footprint', 'vocabularies', 'passkey'].map((key) => ({ key, done: false })),
};

const seeded = { id: 'ta', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm', status: 'active', defaultLanguage: svenska, contentLanguages: [svenska, english], onboarding };
const fresh = { ...seeded, id: 'tn', name: 'Third Bank AB', slug: 'third-bank-ab', defaultLanguage: null, contentLanguages: [] };

/** The server: the tenant as given, the three reference languages, and a PATCH that answers the tenant back. */
function server(tenant: typeof seeded | typeof fresh): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === LANGUAGES_PATH) return { status: 200, data: [svenska, english, suomi] };
    if (sent.path === TENANT_PATH && sent.method === 'get') return { status: 200, data: tenant };
    if (sent.path === TENANT_PATH && sent.method === 'patch') return { status: 200, data: tenant };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

async function renderScreen(): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <OrganisationScreen />
    </Query>,
  );
  await screen.findByLabelText('Timezone');
}

const patches = (sent: Sent[]) => sent.filter((s) => s.method === 'patch' && s.path === TENANT_PATH).map((s) => s.body);

async function save(sent: Sent[], count: number): Promise<unknown> {
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(patches(sent)).toHaveLength(count));
  await screen.findByText('Saved.');
  return patches(sent)[count - 1];
}

beforeEach(() => {
  resetApiForTests();
});

describe('the organisation profile form', () => {
  it('starts the default language on its placeholder for a tenant that has none, and sends it only once chosen', async () => {
    const sent = server(fresh);
    await renderScreen();
    const select = screen.getByLabelText('Default language') as HTMLSelectElement;
    expect(select).toHaveValue('');
    expect(select.selectedOptions[0]).toHaveTextContent('Choose a language');
    expect(screen.getByRole('option', { name: 'Choose a language' })).toBeDisabled();

    // Saving just the timezone sends neither language field: nothing was chosen.
    fireEvent.change(screen.getByLabelText('Timezone'), { target: { value: 'Europe/Helsinki' } });
    expect(await save(sent, 1)).toEqual({ name: 'Third Bank AB', timezone: 'Europe/Helsinki' });

    fireEvent.change(select, { target: { value: 'fi' } });
    expect(await save(sent, 2)).toEqual({ name: 'Third Bank AB', timezone: 'Europe/Helsinki', defaultLanguage: 'fi' });
  });

  it('sends the content languages only when the draft changed them, in the order they were ticked', async () => {
    const sent = server(seeded);
    await renderScreen();
    expect(screen.getByLabelText('Default language')).toHaveValue('sv');

    expect(await save(sent, 1)).toEqual({ name: 'Example Bank AB', timezone: 'Europe/Stockholm', defaultLanguage: 'sv' });

    fireEvent.click(screen.getByRole('checkbox', { name: 'Suomi' }));
    expect(await save(sent, 2)).toEqual({ name: 'Example Bank AB', timezone: 'Europe/Stockholm', defaultLanguage: 'sv', contentLanguages: ['sv', 'en', 'fi'] });
  });

  it('asks for at least one content language instead of emptying the list, and sends nothing', async () => {
    const sent = server(seeded);
    await renderScreen();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Svenska' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'English' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose at least one content language.');
    expect(patches(sent)).toHaveLength(0);
    expect(screen.queryByText('Saved.')).toBeNull();

    // Ticking one again clears the message, and the save goes through with it.
    fireEvent.click(screen.getByRole('checkbox', { name: 'English' }));
    expect(screen.queryByText('Choose at least one content language.')).toBeNull();
    expect(await save(sent, 1)).toMatchObject({ contentLanguages: ['en'] });
  });
});
