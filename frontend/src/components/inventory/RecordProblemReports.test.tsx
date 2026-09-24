import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { ProblemReport } from '@/features/problem-reports/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { RecordProblemReports } from './RecordProblemReports';

// "Reported problems" on a record (AUD-03, INV-06): the bank's reports on it,
// newest first, and the close. The server decides who reads which report; the
// section offers the close only to the reporter and a holder of
// proposals.create, and renders every refusal where it happened.

const READER = ['library.read', 'problems.report'];
const OFFICER = ['library.read', 'problems.report', 'proposals.create'];

const reader = { id: 'u-reader', name: 'Johan Berg' };
const officer = { id: 'u-officer', name: 'Erik Holm' };

const openReport: ProblemReport = {
  id: 'r-open',
  subjectType: 'obligation',
  subjectId: 'ob-1',
  subjectTitle: 'Keep records of client orders',
  subjectReference: 'FFFS 2017:2, 9 kap. 6 §',
  description: 'The retention line says five years; the source says ten.',
  versionNumber: 2,
  language: 'sv',
  reporter: reader,
  status: 'open',
  createdAt: '2026-09-20T09:14:22Z',
  closedBy: null,
  closedAt: null,
  resolutionNote: null,
};
const closedReport: ProblemReport = {
  ...openReport,
  id: 'r-closed',
  description: 'The in-force date looks wrong.',
  versionNumber: null,
  language: null,
  status: 'answered',
  closedBy: officer,
  closedAt: '2026-09-21T13:02:10Z',
  resolutionNote: 'The screen showed version 1.',
};

function meWith(id: string, permissions: string[]) {
  return { user: { id, name: 'Me', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions, enrolmentPending: false };
}

/** The server: /me, the record's reports, and the close. */
function serve(meId: string, permissions: string[], list: () => Answer, close: (sent: Sent) => Answer = () => ({ status: 200, data: {} })) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: meWith(meId, permissions) };
    if (sent.method === 'get') return list();
    return close(sent);
  });
}

function renderSection(permissions: string[]) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <RecordProblemReports subjectType="obligation" subjectId="ob-1" />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

const page = (items: ProblemReport[], total = items.length): Answer => ({ status: 200, data: { items, total } });

function row(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-report-id="${id}"]`);
  if (found === null) throw new Error(`no row ${id}`);
  return found;
}

describe('RecordProblemReports', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it("lists the record's reports with reporter, time, words, what was on screen and a status pill", async () => {
    const sent = serve('u-officer', OFFICER, () => page([openReport, closedReport]));
    renderSection(OFFICER);
    await waitFor(() => expect(document.querySelector('[data-report-id="r-open"]')).not.toBeNull());
    expect(screen.getByRole('heading', { name: 'Reported problems' })).toBeInTheDocument();
    expect(screen.getByText('Every report your organisation filed on this record, newest first.')).toBeInTheDocument();
    expect(document.querySelector('[data-reports-watch]')).toHaveTextContent('the watch re-checks it against its source and proposes the correction');

    const first = row('r-open');
    expect(within(first).getByText('Open')).toBeInTheDocument();
    expect(first).toHaveTextContent('The retention line says five years; the source says ten.');
    expect(first).toHaveTextContent(/Reported by Johan Berg, 20 Sept? 2026/);
    expect(first.querySelector('[data-report-context]')).toHaveTextContent('Version 2, Swedish');

    const second = row('r-closed');
    expect(within(second).getByText('Answered')).toBeInTheDocument();
    expect(second.querySelector('[data-report-context]')).toBeNull();
    expect(second.querySelector('[data-report-note]')).toHaveTextContent('The screen showed version 1.');
    expect(second).toHaveTextContent(/Closed by Erik Holm, 21 Sept? 2026/);
    expect(within(second).queryByRole('button', { name: 'Close report' })).toBeNull();

    expect(sent.filter((s) => s.path === '/api/v1/problem-reports').map((s) => s.params)).toEqual([{ subjectType: 'obligation', subjectId: 'ob-1', limit: 20, offset: 0 }]);
  });

  it("offers a holder of proposals.create the close on a colleague's report", async () => {
    serve('u-officer', OFFICER, () => page([openReport]));
    renderSection(OFFICER);
    await waitFor(() => expect(document.querySelector('[data-report-id="r-open"]')).not.toBeNull());
    await waitFor(() => expect(within(row('r-open')).getByRole('button', { name: 'Close report' })).toBeInTheDocument());
  });

  it('offers a member without it the close on their own report only, and says the list is theirs', async () => {
    const colleagues = { ...openReport, id: 'r-colleague', reporter: officer };
    serve('u-reader', READER, () => page([openReport, colleagues]));
    renderSection(READER);
    await waitFor(() => expect(within(row('r-open')).getByRole('button', { name: 'Close report' })).toBeInTheDocument());
    expect(within(row('r-colleague')).queryByRole('button', { name: 'Close report' })).toBeNull();
    expect(screen.getByText('The reports you filed on this record, newest first.')).toBeInTheDocument();
  });

  it.each(['answered', 'fixed', 'rejected'] as const)('closes a report as %s with the note, trimmed, and refreshes the list', async (status) => {
    let closed = false;
    const sent = serve(
      'u-reader',
      READER,
      () => page([closed ? { ...openReport, status, closedBy: reader, closedAt: '2026-09-22T08:00:00Z', resolutionNote: 'Found it.' } : openReport]),
      () => {
        closed = true;
        return { status: 200, data: {} };
      },
    );
    renderSection(READER);
    await waitFor(() => expect(within(row('r-open')).getByRole('button', { name: 'Close report' })).toBeInTheDocument());
    fireEvent.click(within(row('r-open')).getByRole('button', { name: 'Close report' }));

    const dialog = screen.getByRole('dialog', { name: 'Close this report' });
    fireEvent.change(within(dialog).getByLabelText('Outcome'), { target: { value: status } });
    fireEvent.change(within(dialog).getByLabelText('Note for the reporter'), { target: { value: '  Found it.  ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close report' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(sent.filter((s) => s.method === 'patch').map((s) => [s.path, s.body])).toEqual([['/api/v1/problem-reports/r-open', { status, resolutionNote: 'Found it.' }]]);
    await waitFor(() => expect(row('r-open')).toHaveAttribute('data-report-status', status));
    expect(row('r-open').querySelector('[data-report-note]')).toHaveTextContent('Found it.');
  });

  it('refuses to close without a note: whitespace is not one', async () => {
    const sent = serve('u-reader', READER, () => page([openReport]));
    renderSection(READER);
    await waitFor(() => expect(within(row('r-open')).getByRole('button', { name: 'Close report' })).toBeInTheDocument());
    fireEvent.click(within(row('r-open')).getByRole('button', { name: 'Close report' }));
    const dialog = screen.getByRole('dialog', { name: 'Close this report' });
    const send = within(dialog).getByRole('button', { name: 'Close report' });
    expect(send).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('Note for the reporter'), { target: { value: '   ' } });
    expect(send).toBeDisabled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(sent.filter((s) => s.method === 'patch')).toEqual([]);
  });

  it('renders a 409 in place as already closed, and the list then shows how', async () => {
    let closed = false;
    serve(
      'u-officer',
      OFFICER,
      () => page([closed ? { ...closedReport, id: 'r-open' } : openReport]),
      () => {
        closed = true;
        return { status: 409, data: { code: 'already_closed', detail: 'This report is already closed.' } };
      },
    );
    renderSection(OFFICER);
    await waitFor(() => expect(within(row('r-open')).getByRole('button', { name: 'Close report' })).toBeInTheDocument());
    fireEvent.click(within(row('r-open')).getByRole('button', { name: 'Close report' }));
    const dialog = screen.getByRole('dialog', { name: 'Close this report' });
    fireEvent.change(within(dialog).getByLabelText('Note for the reporter'), { target: { value: 'Answered.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close report' }));

    await waitFor(() => expect(within(dialog).getByRole('alert')).toHaveTextContent('Someone closed this report already. The list now shows how.'));
    expect(within(dialog).getByRole('button', { name: 'Close report' })).toBeDisabled();
    await waitFor(() => expect(row('r-open')).toHaveAttribute('data-report-status', 'answered'));
  });

  it('says so when the record has no report', async () => {
    serve('u-reader', READER, () => page([]));
    renderSection(READER);
    expect(await screen.findByText('No problems reported on this record.')).toBeInTheDocument();
  });

  it('says how many more there are beyond the first page', async () => {
    serve('u-officer', OFFICER, () => page([openReport], 21));
    renderSection(OFFICER);
    expect(await screen.findByText('Showing the newest 1 of 21')).toBeInTheDocument();
  });

  it('shows the loading state, then an error with a retry that reads again', async () => {
    let calls = 0;
    serve('u-reader', READER, () => {
      calls += 1;
      return calls === 1 ? { status: 500, data: { code: 'server_error', detail: 'no' } } : page([]);
    });
    renderSection(READER);
    expect(document.querySelector('[data-loading-state]')).not.toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('No problems reported on this record.')).toBeInTheDocument();
  });

  it("renders the server's refusal in place, naming the permission", async () => {
    serve('u-reader', READER, () => ({ status: 403, data: { code: 'permission_denied', detail: 'You cannot read these reports.', requiredPermission: 'problems.report' } }));
    renderSection(READER);
    expect(await screen.findByRole('alert')).toHaveTextContent('You cannot read these reports. Needs problems report');
  });

  it('renders nothing and asks for nothing without problems.report', async () => {
    const sent = serve('u-other', ['library.read'], () => page([openReport]));
    const { container } = renderSection(['library.read']);
    await waitFor(() => expect(sent.some((s) => s.path === '/api/v1/me')).toBe(true));
    expect(container).toBeEmptyDOMElement();
    expect(sent.some((s) => s.path === '/api/v1/problem-reports')).toBe(false);
  });
});
