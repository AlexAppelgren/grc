import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { LibraryUpdateRow, LibraryUpdatesPage } from '@/features/library-updates/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { LibraryUpdatesScreen } from './LibraryUpdatesScreen';

// /inventory/updates against the generated contract (LibraryUpdatesPage in
// openapi.json): a legal date is an object with its precision, the terms that
// put a duty outside the footprint arrive as `outsideReason`, and "This looks
// wrong" files through the same report form the obligation card uses.

const ME = {
  user: { id: 'u1', name: 'Sara', locale: 'en' },
  tenant: { timezone: 'Europe/Stockholm' },
  permissions: ['library.read', 'problems.report'],
  enrolmentPending: false,
};

// Who stood behind each change: a person approved these, and no agent proposed or
// confirmed them. Spread in, so the rows hold these fields whether or not the
// contract they are typed by names them yet.
const APPROVED_BY_A_PERSON = { verifiedOrigin: 'user', proposedByAgent: null, confirmedByAgent: null };

const newVersion: LibraryUpdateRow = {
  ...APPROVED_BY_A_PERSON,
  id: '8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21',
  kind: 'new_obligation_version',
  appliedAt: '2026-09-18T09:20:00Z',
  effectiveFrom: { date: '2026-10-01', precision: 'quarter' },
  target: {
    id: '3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44',
    title: 'Pay for third-party research only under the permitted models',
    referenceLabel: 'Third-party payments',
    instrumentShortName: 'FFFS 2017:2',
  },
  versionNumber: 2,
  vocabulary: null,
  vocabularyList: null,
  inFootprint: true,
  outsideReason: [],
};

const outside: LibraryUpdateRow = {
  ...newVersion,
  id: '5b0c3e1a-7d42-4c8e-9a61-2f3d4e5a6b7c',
  target: { id: 'ob-exec', title: 'Execute orders on terms most favourable to the client', referenceLabel: 'Best execution', instrumentShortName: 'FFFS 2017:2' },
  inFootprint: false,
  outsideReason: [{ dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'execution_only', kind: null, label: 'Execution only' }] }],
};

const flagRenamed: LibraryUpdateRow = {
  ...APPROVED_BY_A_PERSON,
  id: '0e9d8c7b-6a5f-4e3d-2c1b-0a9f8e7d6c5b',
  kind: 'vocabulary_relabel',
  appliedAt: '2026-09-17T08:00:00Z',
  effectiveFrom: null,
  target: null,
  versionNumber: null,
  vocabulary: { key: 'advice_perimeter', kind: null, label: 'Advice perimeter (RIS)' },
  vocabularyList: 'flag',
  inFootprint: true,
  outsideReason: [],
};

function page(items: LibraryUpdateRow[]): LibraryUpdatesPage {
  return { since: '2026-09-12T07:00:00Z', total: items.length, days: [{ date: '2026-09-18', items }] };
}

/** The server: /me for the format context, the feed (outside rows only when asked for), and the report. */
function serve() {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: ME };
    if (sent.path.endsWith('/problem-reports')) return { status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } };
    const asked = (sent.params ?? {}) as { outsideFootprint?: string };
    return { status: 200, data: page(asked.outsideFootprint === 'true' ? [newVersion, outside, flagRenamed] : [newVersion, flagRenamed]) };
  });
}

function renderIn(permissions: string[] = ['library.read', 'problems.report']) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <LibraryUpdatesScreen />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

function rowOf(id: string): HTMLElement {
  return document.querySelector(`[data-update-id="${id}"]`) as HTMLElement;
}

describe('LibraryUpdatesScreen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('renders a change under the record it touched, with its legal date at the precision it is known to', async () => {
    serve();
    renderIn();
    const title = await screen.findByRole('link', { name: 'Pay for third-party research only under the permitted models' });
    expect(title).toHaveAttribute('href', `/inventory/obligations/${newVersion.target?.id}`);

    const row = rowOf(newVersion.id);
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['New version', 'notice'],
      ['FFFS 2017:2', 'brand'],
    ]);
    expect(within(row).getByText('In force from Q4 2026')).toBeInTheDocument();
    expect(within(row).getByRole('link', { name: 'Show what changed' })).toHaveAttribute('href', `/inventory/obligations/${newVersion.target?.id}`);
    // Filed under the bank's own day (the weekday's punctuation is the ICU build's).
    expect(screen.getByRole('heading', { level: 2, name: /^Friday,? 18 September 2026$/ })).toBeInTheDocument();
  });

  it('names a changed list row by its label and offers no report on a change that names no record', async () => {
    serve();
    renderIn();
    await screen.findByRole('link', { name: 'Pay for third-party research only under the permitted models' });
    const row = rowOf(flagRenamed.id);
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => pill.textContent)).toEqual(['Vocabulary', 'Advice perimeter (RIS)']);
    expect(within(row).queryByText('flag')).not.toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'This looks wrong' })).not.toBeInTheDocument();
  });

  it('shows a duty outside the footprint only when asked, dashed and saying which terms put it there', async () => {
    const sent = serve();
    renderIn();
    await screen.findByRole('link', { name: 'Pay for third-party research only under the permitted models' });
    expect(rowOf(outside.id)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Show outside our scope' }));
    await waitFor(() => expect(rowOf(outside.id)).not.toBeNull());
    expect(rowOf(outside.id)).toHaveAttribute('data-outside-footprint', '');
    expect(within(rowOf(outside.id)).getByText('Outside our scope: Execution only')).toBeInTheDocument();
    expect(rowOf(newVersion.id)).not.toHaveAttribute('data-outside-footprint');
    expect(sent.filter((call) => call.path === '/api/v1/library-updates').map((call) => call.params)).toContainEqual({ outsideFootprint: 'true' });
  });

  it('asks for every vocabulary and term kind at once when the kind filter reads "Vocabulary"', async () => {
    const sent = serve();
    renderIn();
    await screen.findByRole('link', { name: 'Pay for third-party research only under the permitted models' });
    fireEvent.change(screen.getByRole('combobox', { name: 'Kind' }), { target: { value: 'vocabulary_create,vocabulary_relabel,vocabulary_retire,vocabulary_restore,vocabulary_merge,term_create,term_update' } });
    await waitFor(() =>
      expect(sent.filter((call) => call.path === '/api/v1/library-updates').map((call) => call.params)).toContainEqual({
        kind: 'vocabulary_create,vocabulary_relabel,vocabulary_retire,vocabulary_restore,vocabulary_merge,term_create,term_update',
      }),
    );
  });

  it('files "This looks wrong" through the shared report form, on the record and the version the row named', async () => {
    const sent = serve();
    renderIn();
    const row = await waitFor(() => {
      const found = rowOf(newVersion.id);
      expect(found).not.toBeNull();
      return found;
    });
    fireEvent.click(within(row).getByRole('button', { name: 'This looks wrong' }));
    const dialog = await screen.findByRole('dialog', { name: 'What looks wrong?' });
    fireEvent.change(within(dialog).getByLabelText('What you see'), { target: { value: 'The annual review is missing from version 2.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send report' }));
    expect(await within(dialog).findByText('Report sent. Thank you.')).toBeInTheDocument();
    expect(sent.filter((call) => call.path.endsWith('/problem-reports')).map((call) => [call.path, call.body])).toEqual([
      [`/api/v1/obligations/${newVersion.target?.id}/problem-reports`, { description: 'The annual review is missing from version 2.', versionNumber: 2 }],
    ]);

    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('offers no report to a reader who may not file one', async () => {
    serve();
    renderIn(['library.read']);
    await screen.findByRole('link', { name: 'Pay for third-party research only under the permitted models' });
    expect(screen.queryByRole('button', { name: 'This looks wrong' })).not.toBeInTheDocument();
  });
});
