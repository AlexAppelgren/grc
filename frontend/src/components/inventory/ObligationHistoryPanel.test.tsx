import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { AxiosAdapter } from 'axios';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import { HISTORY_PAGE, ObligationHistoryPanel } from './ObligationHistoryPanel';

// "How we read this rule" and the assessment history (REG-04): the current
// reading with its author and date, earlier versions kept readable, a new
// version written under If-Match by register.edit only, a stale write said in
// place, and the history newest first a page at a time.

const EDITOR = ['register.read', 'register.edit'];
const READER = ['register.read'];
const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };
const JOHAN = { id: 'u-johan', name: 'Johan Berg' };

const reading = {
  obligationId: 'ob-1',
  current: { versionNo: 2, text: 'Every instrument outside the list is complex for us.', author: SARA, writtenAt: '2026-08-26T07:00:00Z' },
  earlier: [{ versionNo: 1, text: 'We read warrants as outside the list.', author: JOHAN, writtenAt: '2025-10-30T08:00:00Z' }],
};

function assessment(n: number) {
  return {
    id: `a-${n}`,
    orgUnitId: null,
    orgUnitName: n === 0 ? 'Example Bank AB' : null,
    assessedAt: '2026-08-26T07:00:00Z',
    assessedBy: SARA,
    method: 'second_line_review' as const,
    status: { key: 'compliant', kind: 'compliant', label: 'Compliant' },
    riskRating: null,
    rationale: `Rationale ${n}`,
    nextReviewDate: null,
  };
}

function serve(interpretation: unknown, total: number, write: (sent: Sent) => Answer = () => ({ status: 200, data: reading })) {
  const sent = installAdapter((s) => {
    if (s.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u-sara', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: EDITOR, enrolmentPending: false } };
    if (s.path.endsWith('/interpretation') && s.method === 'get') return { status: 200, data: interpretation };
    if (s.path.endsWith('/assessments')) {
      const { offset = 0 } = (s.params ?? {}) as { offset?: number };
      const count = Math.max(0, Math.min(HISTORY_PAGE, total - offset));
      return { status: 200, data: { items: Array.from({ length: count }, (_, i) => assessment(offset + i)), total } };
    }
    return write(s);
  });
  const inner = api.defaults.adapter as AxiosAdapter;
  const ifMatch: (string | null)[] = [];
  api.defaults.adapter = (config) => {
    if (config.method === 'put') ifMatch.push((config.headers.get('If-Match') as string | undefined) ?? null);
    return inner(config);
  };
  return { sent, ifMatch };
}

function renderPanel(permissions: string[]) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <ObligationHistoryPanel obligationId="ob-1" />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

describe('ObligationHistoryPanel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('shows the current reading with its author and date, keeps the earlier one readable, and offers a reader no editor', async () => {
    serve(reading, 2);
    renderPanel(READER);
    expect(await screen.findByText('Every instrument outside the list is complex for us.')).toBeTruthy();
    expect(screen.getByText(/Version 2, written by Sara Lindqvist/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Write a new version' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Earlier version of how we read this rule, 1' }));
    expect(screen.getByText('We read warrants as outside the list.')).toBeTruthy();
    expect(screen.getByText(/Version 1, written by Johan Berg/)).toBeTruthy();
    expect(await screen.findByText('Rationale 0')).toBeTruthy();
    expect(screen.getAllByText('Second-line review')).toHaveLength(2);
    expect(screen.getByText('Example Bank AB')).toBeTruthy();
  });

  it('writes the first reading with If-Match 0 and says when nothing is recorded yet', async () => {
    const { sent, ifMatch } = serve({ obligationId: 'ob-1', current: null, earlier: [] }, 0);
    renderPanel(EDITOR);
    expect(await screen.findByText(/No reading recorded/)).toBeTruthy();
    expect(await screen.findByText(/No assessment yet/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Write how we read it' }));
    expect(screen.getByText('Saved as version 1 in your name. Earlier versions stay readable.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Our reading'), { target: { value: ' Custody included. ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save version' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'put')?.body).toEqual({ text: 'Custody included.' }));
    expect(ifMatch).toEqual(['"0"']);
  });

  it('writes the next version against the current one, and says a stale write in place with Reload', async () => {
    const { ifMatch } = serve(reading, 1, () => ({ status: 409, data: { code: 'stale_write', detail: 'server words' } }));
    renderPanel(EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Write a new version' }));
    expect((screen.getByLabelText('Our reading') as HTMLTextAreaElement).value).toBe(reading.current.text);
    fireEvent.click(screen.getByRole('button', { name: 'Save version' }));
    expect(await screen.findByText(/Someone saved a new version while you were writing/)).toBeTruthy();
    expect(ifMatch).toEqual(['"2"']);
    expect((screen.getByRole('button', { name: 'Save version' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('pages the history newest first, older and back', async () => {
    const { sent } = serve(reading, HISTORY_PAGE + 3);
    renderPanel(READER);
    expect(await screen.findByText(`1 to ${HISTORY_PAGE} of ${HISTORY_PAGE + 3}`)).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Newer' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Older' }));
    expect(await screen.findByText(`Rationale ${HISTORY_PAGE}`)).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Older' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Newer' }));
    expect(await screen.findByText('Rationale 0')).toBeTruthy();
    expect(sent.filter((s) => s.path.endsWith('/assessments')).map((s) => s.params)).toContainEqual({ limit: HISTORY_PAGE, offset: HISTORY_PAGE });
  });
});
