import type { AxiosAdapter } from 'axios';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { VocabularyScreen } from '@/components/admin/VocabularyScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { REFRESH_PATH, api, pathOf } from '@/shared/utils/api-client';

// A library list on the tenant surface lists what this bank itself proposed
// on it and is still waiting on (VOC-07, PRO-01), read from GET
// /tenant/proposals filtered to open proposals on this list. The console
// holds library lists too but never reads a bank's own proposals.

const LISTS_PATH = '/api/v1/vocab';
const VALUES_PATH = '/api/v1/vocab/flag';
const PENDING_PATH = '/api/v1/tenant/proposals';

const flags = { list: 'flag', tier: 2, kind: null, count: 1, retiredCount: 0, proposable: true };
const derivatives = {
  key: 'derivatives',
  kind: null,
  label: 'Derivatives',
  labels: { en: 'Derivatives' },
  usageNote: '',
  sortOrder: 1,
  active: true,
  isSystem: false,
  isDefault: false,
  usageCount: 0,
  extra: {},
};
const waiting = { id: 'p-1', kind: 'vocabulary_create', status: 'open', title: 'Add "Outsourcing" to flag', createdAt: '2026-09-16T07:12:00Z' };

/** The server: one library list with one value, and the bank's own proposals as `pending` answers. */
function server(pending: Answer): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === LISTS_PATH) return { status: 200, data: { items: [flags], total: 1 } };
    if (sent.path === VALUES_PATH) return { status: 200, data: { items: [derivatives], total: 1 } };
    if (sent.path === PENDING_PATH) return pending;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

async function renderScreen(surface: 'tenant' | 'console' = 'tenant'): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={['vocab.manage', 'proposals.create', 'library_vocab.manage']}>
        <VocabularyScreen list="flag" surface={surface} />
      </PermissionsProvider>
    </Query>,
  );
  await screen.findAllByText('Derivatives');
}

const pendingReads = (sent: Sent[]) => sent.filter((s) => s.path === PENDING_PATH);
const pendingPanel = () => document.querySelector('[data-pending-proposals]') as HTMLElement;

beforeEach(() => {
  resetApiForTests();
});

describe('what this bank proposed on a library list', () => {
  it('reads only open proposals on this list, and says so when none is waiting', async () => {
    const sent = server({ status: 200, data: { items: [], total: 0 } });
    await renderScreen();
    expect(await within(pendingPanel()).findByText('Nothing you suggested on this list is waiting for review.')).toBeVisible();
    expect(pendingReads(sent).map((s) => s.params)).toEqual([{ status: 'open', targetList: 'flag' }]);
  });

  it('shows a loading state until the answer comes', async () => {
    server({ status: 200, data: { items: [waiting], total: 1 } });
    // The pending read alone is held back until released; the rest answers at once.
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const scripted = api.defaults.adapter as AxiosAdapter;
    api.defaults.adapter = async (config) => {
      if (pathOf(config) === PENDING_PATH) await held;
      return scripted(config);
    };
    await renderScreen();
    expect(within(pendingPanel()).getByRole('status')).toHaveAttribute('aria-busy', 'true');
    release();
    expect(await within(pendingPanel()).findByText(waiting.title)).toBeVisible();
  });

  it('lists a waiting proposal by its title, marked as waiting, and not as a row of the list', async () => {
    server({ status: 200, data: { items: [waiting], total: 1 } });
    await renderScreen();
    const panel = pendingPanel();
    const row = (await within(panel).findByText(waiting.title)).closest('[data-pending-proposal]') as HTMLElement;
    expect(row).toHaveAttribute('data-pending-proposal', 'p-1');
    expect(within(row).getByText('Waiting for review')).toBeVisible();
    expect(document.querySelector('[data-vocabulary-values="flag"]')).not.toHaveTextContent('Outsourcing');
  });

  it('says so when the proposals cannot be read, and reads them again on retry', async () => {
    const sent = server({ status: 500, data: { code: 'server_error', detail: 'Boom.' } });
    await renderScreen();
    expect(await within(pendingPanel()).findByText('Your suggestions waiting for review could not be loaded.')).toBeVisible();
    fireEvent.click(within(pendingPanel()).getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(pendingReads(sent)).toHaveLength(2));
    // The rest of the screen stands: the list's own value is still shown.
    expect(screen.getAllByText('Derivatives')[0]).toBeVisible();
  });

  it('is never rendered, nor read, on the console surface', async () => {
    const sent = server({ status: 200, data: { items: [waiting], total: 1 } });
    await renderScreen('console');
    expect(pendingPanel()).toBeNull();
    expect(pendingReads(sent)).toHaveLength(0);
  });
});

// The Suggested tab of a tenant list (VOC-03): what members without
// vocab.manage suggested from a picker, for a holder of vocab.manage to add
// (a create with the suggestion's key, which answers it) or decline.
describe('the suggestions waiting on a tenant list', () => {
  const TAGS_PATH = '/api/v1/vocab/tenant_tag';
  const SUGGESTIONS_PATH = '/api/v1/vocab/tenant_tag/suggestions';
  const tags = { list: 'tenant_tag', tier: 3, kind: null, count: 1, retiredCount: 0, proposable: false };
  const pension = {
    id: 's-1',
    list: 'tenant_tag',
    key: 'pension_transfers',
    labels: { en: 'Pension transfers' },
    usageNote: 'Moving a pension between providers.',
    suggestedBy: { id: 'u-1', name: 'Johan Berg' },
    status: 'pending',
    createdAt: '2026-09-17T08:00:00Z',
  };

  function tenantServer(suggestions: Answer, write: Answer = { status: 201, data: {} }): Sent[] {
    return installAdapter((sent) => {
      if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
      if (sent.path === LISTS_PATH) return { status: 200, data: { items: [tags], total: 1 } };
      if (sent.path === TAGS_PATH && sent.method === 'get') return { status: 200, data: { items: [derivatives], total: 1 } };
      if (sent.path === SUGGESTIONS_PATH) return suggestions;
      if (sent.method === 'post') return write;
      return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
    });
  }

  async function renderTags(permissions: string[] = ['vocab.manage']): Promise<void> {
    const { wrapper: Query } = queryWrapper();
    render(
      <Query>
        <PermissionsProvider permissions={permissions}>
          <VocabularyScreen list="tenant_tag" />
        </PermissionsProvider>
      </Query>,
    );
    await screen.findAllByText('Derivatives');
  }

  const suggestionReads = (sent: Sent[]) => sent.filter((s) => s.path === SUGGESTIONS_PATH);

  it('counts them on the tab and lists each with who suggested it, when, and why', async () => {
    tenantServer({ status: 200, data: { items: [pension], total: 1 } });
    await renderTags();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggested (1)' }));
    const row = document.querySelector('[data-suggestion="s-1"]') as HTMLElement;
    expect(within(row).getAllByText('Pension transfers')[0]).toBeVisible();
    expect(within(row).getByText(/^Suggested by Johan Berg, 17 Sept? 2026$/)).toBeVisible();
    expect(within(row).getByText('Moving a pension between providers.')).toBeVisible();
    expect(document.querySelector('[data-vocabulary-values]')).toBeNull();
  });

  it('adds a suggestion as a value with its key, labels and note, which answers it', async () => {
    const sent = tenantServer({ status: 200, data: { items: [pension], total: 1 } });
    await renderTags();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggested (1)' }));
    fireEvent.click(within(document.querySelector('[data-suggestion="s-1"]') as HTMLElement).getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH)).toHaveLength(1));
    const post = sent.find((s) => s.method === 'post' && s.path !== REFRESH_PATH);
    expect([post?.path, post?.body]).toEqual([TAGS_PATH, { key: 'pension_transfers', labels: { en: 'Pension transfers' }, usageNote: 'Moving a pension between providers.' }]);
    // The inbox is read again, so the answered suggestion leaves it.
    await waitFor(() => expect(suggestionReads(sent).length).toBeGreaterThanOrEqual(2));
  });

  it('declines a suggestion by its id', async () => {
    const sent = tenantServer({ status: 200, data: { items: [pension], total: 1 } }, { status: 200, data: { ...pension, status: 'declined' } });
    await renderTags();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggested (1)' }));
    fireEvent.click(screen.getByRole('button', { name: 'Decline' }));
    await waitFor(() => expect(sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH).map((s) => s.path)).toEqual(['/api/v1/vocab/tenant_tag/suggestions/s-1/decline']));
  });

  it.each([
    [{ status: 422, data: { code: 'near_duplicate', detail: 'Too close.', candidates: [{ key: 'pensions', label: 'Pensions' }] } }, 'Did you mean Pensions?'],
    [{ status: 409, data: { code: 'duplicate_key', detail: 'Taken.', candidates: [{ key: 'pensions', label: 'Pensions' }] } }, '"Pensions" already exists.'],
    [{ status: 500, data: { code: 'server_error', detail: 'Could not save.' } }, /^Could not save\./],
  ])('says why an add was refused, by the refusal: %#', async (answer, words) => {
    tenantServer({ status: 200, data: { items: [pension], total: 1 } }, answer);
    await renderTags();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggested (1)' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByText(words)).toBeVisible();
  });

  it('says so when nothing is waiting, and when the suggestions cannot be read', async () => {
    tenantServer({ status: 200, data: { items: [], total: 0 } });
    await renderTags();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggested (0)' }));
    expect(screen.getByText('Nothing is waiting')).toBeVisible();

    resetApiForTests();
    cleanup();
    const sent = tenantServer({ status: 500, data: { code: 'server_error', detail: 'Boom.' } });
    await renderTags();
    fireEvent.click(await screen.findByRole('button', { name: /^Suggested/ }));
    expect(await screen.findByText('Could not load the suggestions')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(suggestionReads(sent)).toHaveLength(2));
  });

  it('is neither shown nor read without vocab.manage, nor on a library list', async () => {
    const sent = tenantServer({ status: 200, data: { items: [pension], total: 1 } });
    await renderTags([]);
    expect(screen.queryByRole('button', { name: /^Suggested/ })).toBeNull();
    expect(suggestionReads(sent)).toHaveLength(0);

    cleanup();
    const library = server({ status: 200, data: { items: [], total: 0 } });
    await renderScreen();
    expect(screen.queryByRole('button', { name: /^Suggested/ })).toBeNull();
    expect(library.filter((s) => s.path.endsWith('/suggestions'))).toHaveLength(0);
  });
});

// The jurisdictions on the console (ADM-02, D-94): a list of fixed keys. The
// seed files every market, so nothing is added or merged here; a library
// editor proposes new labels, one per content language, a retirement or a
// restore, a seeded market included, and each waits for a second editor.
describe('the jurisdictions on the console', () => {
  const JURISDICTIONS_PATH = '/api/v1/vocab/jurisdiction';
  const LANGUAGES_PATH = '/api/v1/reference/languages';
  const summary = { list: 'jurisdiction', tier: 2, kind: 'jurisdiction_kind', kinds: ['country'], count: 1, retiredCount: 1, proposable: true };
  const denmark = {
    key: 'dk',
    kind: 'country',
    label: 'Denmark',
    labels: { en: 'Denmark', sv: 'Danmark' },
    usageNote: '',
    sortOrder: 2,
    active: true,
    isSystem: true,
    isDefault: false,
    usageCount: 64,
    extra: {},
    version: 3,
  };
  const iceland = { ...denmark, key: 'is', label: 'Iceland', labels: { en: 'Iceland' }, active: false, usageCount: 0, version: 1 };
  const languages = [
    { key: 'da', kind: null, label: 'Dansk' },
    { key: 'en', kind: null, label: 'English' },
    { key: 'sv', kind: null, label: 'Svenska' },
  ];
  const proposal = (kind: string, title: string) => ({ status: 202, data: { proposal: { id: 'p-9', kind, status: 'open', title } } });

  function jurisdictionServer(write: Answer): Sent[] {
    return installAdapter((sent) => {
      if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
      if (sent.path === LISTS_PATH) return { status: 200, data: { items: [summary], total: 1 } };
      if (sent.path === JURISDICTIONS_PATH && sent.method === 'get') return { status: 200, data: { items: [denmark, iceland], total: 2 } };
      if (sent.path === LANGUAGES_PATH) return { status: 200, data: languages };
      if (sent.method === 'post' || sent.method === 'patch') return write;
      return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
    });
  }

  async function renderJurisdictions(): Promise<void> {
    const { wrapper: Query } = queryWrapper();
    render(
      <Query>
        <PermissionsProvider permissions={['library_vocab.manage']}>
          <VocabularyScreen list="jurisdiction" surface="console" />
        </PermissionsProvider>
      </Query>,
    );
    await screen.findAllByText('Denmark');
  }

  const row = (key: string) => document.querySelector(`[data-value-key="${key}"]`) as HTMLElement;
  const writes = (sent: Sent[]) => sent.filter((s) => s.method !== 'get' && s.path !== REFRESH_PATH);

  it('offers new labels and a retirement on a seeded market, and never an addition or a merge', async () => {
    jurisdictionServer({ status: 500 });
    await renderJurisdictions();
    expect(screen.getByText(/A market's key never changes/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Suggest a change' })).toBeNull();
    expect(within(row('dk')).getByRole('button', { name: 'Edit labels' })).toBeVisible();
    expect(within(row('dk')).getByRole('button', { name: 'Retire' })).toBeVisible();
    expect(within(row('dk')).queryByRole('button', { name: /^Merge into/ })).toBeNull();
    expect(within(row('dk')).queryByRole('button', { name: 'Rename' })).toBeNull();
  });

  it('proposes a label per content language, keeping the key, and says it is waiting for review', async () => {
    const sent = jurisdictionServer(proposal('vocabulary_relabel', 'Change dk on jurisdiction'));
    await renderJurisdictions();
    fireEvent.click(within(row('dk')).getByRole('button', { name: 'Edit labels' }));
    const form = (await screen.findByRole('form', { name: 'Labels for Denmark' })) as HTMLElement;
    expect(await within(form).findByLabelText('English')).toHaveValue('Denmark');
    expect(within(form).getByLabelText('Svenska')).toHaveValue('Danmark');
    expect(within(form).getByLabelText('Dansk')).toHaveValue('');
    expect(within(form).getByText('Key dk. The key never changes; only the labels do.')).toBeVisible();
    expect(within(form).getByText(/scope term in every bank's Regulatory scope follows/)).toBeVisible();

    fireEvent.change(within(form).getByLabelText('Dansk'), { target: { value: 'Kongeriget Danmark' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Send for review' }));
    expect(await screen.findByText('Change dk on jurisdiction is waiting for review.')).toBeVisible();
    expect(writes(sent).map((s) => [s.method, s.path, s.body])).toEqual([
      ['patch', `${JURISDICTIONS_PATH}/dk`, { labels: { da: 'Kongeriget Danmark', en: 'Denmark', sv: 'Danmark' } }],
    ]);
  });

  it('asks for a label before it sends anything', async () => {
    const sent = jurisdictionServer(proposal('vocabulary_relabel', 'Change dk on jurisdiction'));
    await renderJurisdictions();
    fireEvent.click(within(row('dk')).getByRole('button', { name: 'Edit labels' }));
    const form = (await screen.findByRole('form', { name: 'Labels for Denmark' })) as HTMLElement;
    fireEvent.change(await within(form).findByLabelText('English'), { target: { value: ' ' } });
    fireEvent.change(within(form).getByLabelText('Svenska'), { target: { value: '' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Send for review' }));
    expect(await within(form).findByText('Give the value a label.')).toBeVisible();
    expect(writes(sent)).toEqual([]);
  });

  it('proposes a retirement, naming what follows, and says it is waiting for review', async () => {
    const sent = jurisdictionServer(proposal('vocabulary_retire', 'Retire dk from jurisdiction'));
    await renderJurisdictions();
    fireEvent.click(within(row('dk')).getByRole('button', { name: 'Retire' }));
    const dialog = await screen.findByRole('dialog', { name: 'Retire "Denmark"?' });
    expect(within(dialog).getByText(/its scope term is retired with it/)).toBeVisible();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send for review' }));
    expect(await within(dialog).findByText('Retire dk from jurisdiction is waiting for review.')).toBeVisible();
    expect(writes(sent).map((s) => [s.path, s.body])).toEqual([[`${JURISDICTIONS_PATH}/dk/retire`, { confirm: true }]]);
  });

  it('proposes a restore of a retired market, and says it is waiting for review', async () => {
    const sent = jurisdictionServer(proposal('vocabulary_restore', 'Restore is to jurisdiction'));
    await renderJurisdictions();
    fireEvent.click(screen.getByRole('button', { name: 'Retired' }));
    fireEvent.click(within(row('is')).getByRole('button', { name: 'Restore' }));
    expect(await within(row('is')).findByText('Restore is to jurisdiction is waiting for review.')).toBeVisible();
    expect(writes(sent).map((s) => s.path)).toEqual([`${JURISDICTIONS_PATH}/is/restore`]);
  });
});
