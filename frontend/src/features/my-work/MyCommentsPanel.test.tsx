import { fireEvent, render, screen } from '@testing-library/react';
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
});
