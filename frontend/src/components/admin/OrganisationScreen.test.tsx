import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { OrganisationScreen } from '@/components/admin/OrganisationScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';

// The Organisation profile form (TEN-01, ADM-S17) saves what it says: an
// omitted field is left alone by the server, and an empty list of content
// languages is refused there. So the form sends the languages only when the
// draft changed them, refuses to empty them before sending anything, and
// leaves the default language unset until a person chooses one; a tenant
// created from the console starts with neither (D-68).

const TENANT_PATH = '/api/v1/tenant';
const AI_PATH = '/api/v1/tenant/ai';
const LANGUAGES_PATH = '/api/v1/reference/languages';

const svenska = { key: 'sv', kind: null, label: 'Svenska' };
const english = { key: 'en', kind: null, label: 'English' };
const suomi = { key: 'fi', kind: null, label: 'Suomi' };

const onboarding = {
  stepsDone: 0,
  steps: ['profile', 'members', 'footprint', 'vocabularies', 'passkey'].map((key) => ({ key, done: false })),
};

const seeded = { id: 'ta', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm', status: 'active', defaultLanguage: svenska, contentLanguages: [svenska, english], aiEnabled: true, onboarding };
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

// The organisation's own switch over Ask and AI drafts (D-07, SRC-03): a security
// change, so the server asks for a passkey (the api client opens the prompt on
// step_up_required and retries once) and refuses a member without security.manage.
// The profile's Save never sends it.

type Answer = { status: number; data: unknown };

/** The server for the switch: the tenant as given, and each PUT answered by `answer` (by default, the tenant switched). */
function aiServer(tenant: typeof seeded, answer?: (count: number) => Answer): Sent[] {
  let puts = 0;
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === LANGUAGES_PATH) return { status: 200, data: [svenska, english, suomi] };
    if (sent.path === TENANT_PATH && sent.method === 'get') return { status: 200, data: tenant };
    if (sent.path === AI_PATH && sent.method === 'put') {
      puts += 1;
      const enabled = (sent.body as { enabled: boolean }).enabled;
      return answer === undefined ? { status: 200, data: { ...tenant, aiEnabled: enabled } } : answer(puts);
    }
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

const aiPuts = (sent: Sent[]) => sent.filter((s) => s.method === 'put' && s.path === AI_PATH).map((s) => s.body);
const stepUpRequired: Answer = { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.', status: 403 } };

describe('the Ask and AI drafts switch', () => {
  it('reads as on for this organisation and switches off', async () => {
    const sent = aiServer(seeded);
    await renderScreen();
    expect(screen.getByText('On for Example Bank AB. Members can ask questions and have a model draft text for them.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Switch off' }));
    expect(await screen.findByText('Off for Example Bank AB. Ask and AI drafts are refused, and nothing of yours is sent to a model.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Switch on' })).toBeEnabled();
    expect(aiPuts(sent)).toEqual([{ enabled: false }]);
    expect(patches(sent)).toHaveLength(0);
  });

  it('reads as off and switches back on', async () => {
    const sent = aiServer({ ...seeded, aiEnabled: false });
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Switch on' }));
    expect(await screen.findByRole('button', { name: 'Switch off' })).toBeEnabled();
    expect(aiPuts(sent)).toEqual([{ enabled: true }]);
  });

  it('shows it is switching, and takes no second click, while the passkey prompt is open', async () => {
    let confirm: (given: boolean) => void = () => undefined;
    const sent = aiServer(seeded, (count) => (count === 1 ? stepUpRequired : { status: 200, data: { ...seeded, aiEnabled: false } }));
    setStepUpHandler(
      () =>
        new Promise<boolean>((resolve) => {
          confirm = resolve;
        }),
    );
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Switch off' }));
    const busy = await screen.findByRole('button', { name: 'Switching…' });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    expect(aiPuts(sent)).toHaveLength(1);
    confirm(true);
    expect(await screen.findByRole('button', { name: 'Switch on' })).toBeEnabled();
    expect(aiPuts(sent)).toHaveLength(2);
  });

  it('asks for the passkey when the server wants a step-up, and retries once it is given', async () => {
    const sent = aiServer(seeded, (count) => (count === 1 ? stepUpRequired : { status: 200, data: { ...seeded, aiEnabled: false } }));
    const prompts: number[] = [];
    setStepUpHandler(() => {
      prompts.push(1);
      return Promise.resolve(true);
    });
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Switch off' }));
    expect(await screen.findByRole('button', { name: 'Switch on' })).toBeEnabled();
    expect(prompts).toHaveLength(1);
    expect(aiPuts(sent)).toEqual([{ enabled: false }, { enabled: false }]);
  });

  it('changes nothing when the passkey prompt is cancelled, and says so', async () => {
    const sent = aiServer(seeded, () => stepUpRequired);
    setStepUpHandler(() => Promise.resolve(false));
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Switch off' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nothing changed. Switching needs your passkey.');
    expect(screen.getByRole('button', { name: 'Switch off' })).toBeEnabled();
    expect(screen.getByText('On for Example Bank AB. Members can ask questions and have a model draft text for them.')).toBeInTheDocument();
    expect(aiPuts(sent)).toHaveLength(1);
  });

  it('renders the server\'s refusal in place for a member without security.manage', async () => {
    aiServer(seeded, () => ({ status: 403, data: { code: 'permission_denied', detail: 'You do not have permission to do this.', status: 403, requiredPermission: 'security.manage' } }));
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Switch off' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('You do not have permission to do this.');
    expect(alert).toHaveAttribute('data-problem-code', 'permission_denied');
    expect(screen.getByRole('button', { name: 'Switch off' })).toBeEnabled();
  });
});
