import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MyComment } from '@/features/collab/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { MyCommentsPanel } from './MyCommentsPanel';

// "Comments and mentions" (COL-S12): Mentions first, each row the record's
// title linking to where the comment was written; My comments on the other
// tab; a kind the role cannot open named in one line; no composer here.

const ERIK = { id: 'u-erik', name: 'Erik Holm' };
const ANNA = { id: 'u-anna', name: 'Anna Nilsson' };

function comment(id: string, extra: Partial<MyComment>): MyComment {
  return {
    id,
    subjectType: 'obligation',
    subjectId: 'ob-1',
    subjectTitle: 'Pay for third-party research only under the permitted models',
    changeId: null,
    body: 'Please check the custody angle.',
    mentions: [ANNA],
    author: ERIK,
    createdAt: '2026-09-18T12:20:00Z',
    editedAt: null,
    deletedAt: null,
    canEdit: false,
    canDelete: false,
    ...extra,
  };
}

const onCase = comment('c-1', { subjectType: 'change_case', subjectId: 'case-1', changeId: 'ch-1', subjectTitle: 'FI adopts amended rules on paying for investment research' });
const mine = comment('c-2', { author: ANNA, mentions: [], createdAt: '2026-09-19T08:05:00Z' });

function shell(children: ReactNode): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
}

function serve(kinds: string[] = []): Sent[] {
  return installAdapter((sent) => {
    if (sent.path !== '/api/v1/me/comments') return { status: 401, data: { code: 'unauthenticated', detail: 'No session in this test.' } };
    const about = (sent.params as { about: string }).about;
    return { status: 200, data: about === 'mentioned' ? { items: [onCase], total: 1, permissionLimitedKinds: kinds } : { items: [mine], total: 1, permissionLimitedKinds: [] } };
  });
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-09-19T10:00:00Z'));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('MyCommentsPanel', () => {
  it('lists mentions first, linking a case comment to its change page, then my own comments', async () => {
    const sent = serve();
    render(shell(<MyCommentsPanel />));

    expect(await screen.findByRole('link', { name: onCase.subjectTitle })).toHaveAttribute('href', '/watch/ch-1');
    expect(screen.getByText('Erik Holm mentioned you')).toBeInTheDocument();
    expect(screen.getByText('Yesterday 14:20')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Mentions' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByText(onCase.body ?? '')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'My comments' }));
    expect(await screen.findByRole('link', { name: mine.subjectTitle })).toHaveAttribute('href', '/inventory/obligations/ob-1');
    expect(screen.getByText('Today 10:05')).toBeInTheDocument();
    expect(sent.filter((s) => s.path === '/api/v1/me/comments').map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/me/comments', { about: 'mentioned', limit: 20, offset: 0 }],
      ['/api/v1/me/comments', { about: 'written', limit: 20, offset: 0 }],
    ]);
  });

  it('names a kind the role cannot open, never a record', async () => {
    serve(['change_case']);
    render(shell(<MyCommentsPanel />));

    expect(await screen.findByText('Cases are not shown here, because your role cannot open them')).toBeInTheDocument();
  });

  it('names a comment on a record with no page of its own without a link', async () => {
    const internal = comment('c-3', { subjectType: 'internal_item', subjectId: 'ii-1', subjectTitle: 'Complaints procedure' });
    installAdapter(() => ({ status: 200, data: { items: [internal], total: 1, permissionLimitedKinds: [] } }));
    render(shell(<MyCommentsPanel />));

    const row = await screen.findByText('Complaints procedure');
    expect(row.tagName).toBe('H3');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('says there is nothing yet on an empty tab, and goes back to Mentions from My comments', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0, permissionLimitedKinds: [] } }));
    render(shell(<MyCommentsPanel />));

    expect(await screen.findByText('No comments yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'My comments' }));
    await waitFor(() => expect(screen.getByRole('tab', { name: 'My comments' })).toHaveAttribute('aria-selected', 'true'));
    fireEvent.click(screen.getByRole('tab', { name: 'Mentions' }));
    expect(screen.getByRole('tab', { name: 'Mentions' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('No comments yet')).toBeInTheDocument();
    // Back on Mentions the cached page shows at once and is read again.
    expect(sent.map((s) => (s.params as { about: string }).about)).toEqual(['mentioned', 'written', 'mentioned']);
  });

  it('offers a retry when the comments cannot be read, and lists them once it succeeds', async () => {
    let failing = true;
    installAdapter(() =>
      failing ? { status: 503, data: { code: 'unavailable', detail: 'Down in this test.' } } : { status: 200, data: { items: [onCase], total: 1, permissionLimitedKinds: [] } },
    );
    render(shell(<MyCommentsPanel />));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the comments. Check your connection and try again.');
    failing = false;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('link', { name: onCase.subjectTitle })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows more from the next page while the total runs past what is loaded', async () => {
    const sent = installAdapter((s) => {
      if (s.path !== '/api/v1/me/comments') return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
      const offset = (s.params as { offset: number }).offset;
      return { status: 200, data: { items: [offset === 0 ? onCase : { ...mine, id: 'c-21', subjectTitle: 'Second page comment' }], total: 21, permissionLimitedKinds: [] } };
    });
    render(shell(<MyCommentsPanel />));

    await screen.findByRole('link', { name: onCase.subjectTitle });
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));
    expect(await screen.findByRole('link', { name: 'Second page comment' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: onCase.subjectTitle })).toBeInTheDocument();
    expect(sent.filter((s) => s.path === '/api/v1/me/comments').map((s) => (s.params as { offset: number }).offset)).toEqual([0, 1]);
  });
});
