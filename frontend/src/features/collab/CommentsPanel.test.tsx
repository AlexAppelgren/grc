import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AxiosError } from 'axios';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ObligationCommentsPanel } from '@/components/inventory/ObligationCommentsPanel';
import { ChangeCommentsPanel } from '@/components/watch/ChangeCommentsPanel';
import type { CasePanelProps } from '@/features/cases/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { CommentsPanel } from './CommentsPanel';
import type { Comment } from './types';

// The one comments panel (design/system/comments-and-mentions.md): oldest
// first with author, time and "Edited"; the visibility line exactly as the
// card words it; Edit and Delete only where the server says so; a closed edit
// window said in place; the deleted marker; a mention that reached nobody
// named once; and the obligation and the change page mounting this same panel.

const ME = { user: { id: 'u-1', name: 'Sara Lind', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: ['comments.write'], enrolmentPending: false };
const SARA = { id: 'u-1', name: 'Sara Lind' };
const JOHAN = { id: 'u-2', name: 'Johan Berg' };
const SUBJECT = { subjectType: 'change_case', subjectId: 'case-1' };

// "Now" is fixed; every instant below is on 2026-09-25 or the day before, Stockholm time.
const NOW = new Date('2026-09-25T12:30:00Z');

function comment(id: string, over: Partial<Comment> = {}): Comment {
  return {
    id,
    author: JOHAN,
    body: `Body of ${id}`,
    createdAt: '2026-09-25T12:20:00Z',
    editedAt: null,
    deletedAt: null,
    canEdit: false,
    canDelete: false,
    mentions: [],
    subjectType: SUBJECT.subjectType,
    subjectId: SUBJECT.subjectId,
    ...over,
  };
}

type Script = (sent: Sent) => Answer | undefined;

function serve(comments: Comment[], script: Script = () => undefined): Sent[] {
  return installAdapter((sent) => {
    const scripted = script(sent);
    if (scripted !== undefined) return scripted;
    if (sent.path === '/api/v1/me') return { status: 200, data: ME };
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: [SARA, JOHAN] };
    if (sent.path === '/api/v1/comments' && sent.method === 'get') return { status: 200, data: { items: comments, total: comments.length } };
    return { status: 500 };
  });
}

function renderIn(node: ReactNode, permissions: string[] = ['comments.write']) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

const rowOf = (id: string) => document.querySelector<HTMLElement>(`[data-comment-id="${id}"]`)!;

describe('CommentsPanel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('lists the thread oldest first with author, time and Edited, and says who can read it', async () => {
    const sent = serve([
      comment('c-1', { author: SARA, createdAt: '2026-09-24T07:02:00Z' }),
      comment('c-2', { createdAt: '2026-09-25T12:20:00Z', editedAt: '2026-09-25T12:25:00Z' }),
    ]);
    renderIn(<CommentsPanel subject={SUBJECT} />);

    await screen.findByText('Body of c-1');
    const rows = [...document.querySelectorAll('[data-comment-id]')].map((el) => el.getAttribute('data-comment-id'));
    expect(rows).toEqual(['c-1', 'c-2']);
    expect(within(rowOf('c-1')).getByText('Sara Lind')).toBeInTheDocument();
    expect(within(rowOf('c-1')).getByText('Yesterday 09:02')).toBeInTheDocument();
    expect(within(rowOf('c-1')).queryByText('Edited')).toBeNull();
    expect(within(rowOf('c-2')).getByText('Today 14:20')).toBeInTheDocument();
    expect(within(rowOf('c-2')).getByText('Edited')).toBeInTheDocument();
    expect(within(screen.getByRole('heading', { name: /^Comments/ })).getByText('2')).toBeInTheDocument();
    // Verbatim from the card, identical on every surface.
    expect(document.querySelector('[data-visibility-line]')?.textContent).toBe('Everyone in your organisation can read comments.');
    expect(sent.find((s) => s.path === '/api/v1/comments')?.params).toEqual({ ...SUBJECT, limit: 20, offset: 0 });
  });

  it('offers Edit and Delete only where the server allows them, whoever wrote the comment', async () => {
    serve([
      comment('c-1', { author: SARA, canEdit: true, canDelete: true }),
      comment('c-2', { author: SARA, canDelete: true }),
      comment('c-3', { author: SARA }),
    ]);
    renderIn(<CommentsPanel subject={SUBJECT} />);

    await screen.findByText('Body of c-1');
    expect(within(rowOf('c-1')).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(within(rowOf('c-1')).getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(within(rowOf('c-2')).queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(within(rowOf('c-2')).getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(within(rowOf('c-3')).queryByRole('button')).toBeNull();
  });

  it('saves an edit, and says in place when the edit window has closed', async () => {
    let closed = false;
    const sent = serve([comment('c-1', { author: SARA, canEdit: true, canDelete: true })], (s) =>
      s.method === 'patch' ? (closed ? { status: 409, data: { code: 'edit_window_closed', detail: 'Too late.' } } : { status: 200, data: comment('c-1') }) : undefined,
    );
    renderIn(<CommentsPanel subject={SUBJECT} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Edit' }), { target: { value: 'Corrected text' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save' })).toBeNull());
    expect(sent.find((s) => s.method === 'patch')).toMatchObject({ path: '/api/v1/comments/c-1', body: { body: 'Corrected text' } });

    closed = true;
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const alert = await within(rowOf('c-1')).findByRole('alert');
    expect(alert).toHaveTextContent('This comment can no longer be edited');
    expect(alert).toHaveAttribute('data-problem-code', 'edit_window_closed');
  });

  it('asks once before deleting, and shows a deleted comment as a marker without its text', async () => {
    const sent = serve(
      [comment('c-1', { author: SARA, canDelete: true }), comment('c-2', { body: null, deletedAt: '2026-09-25T12:22:00Z', editedAt: '2026-09-25T12:21:00Z' })],
      (s) => (s.method === 'delete' ? { status: 204 } : undefined),
    );
    renderIn(<CommentsPanel subject={SUBJECT} />);

    await screen.findByText('Body of c-1');
    expect(within(rowOf('c-2')).getByText('Comment deleted')).toBeInTheDocument();
    expect(within(rowOf('c-2')).queryByText('Edited')).toBeNull();
    expect(within(rowOf('c-2')).queryByRole('button')).toBeNull();

    fireEvent.click(within(rowOf('c-1')).getByRole('button', { name: 'Delete' }));
    const confirm = within(rowOf('c-1')).getByRole('group', { name: 'Delete this comment?' });
    expect(sent.some((s) => s.method === 'delete')).toBe(false);
    fireEvent.click(within(confirm).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'delete')?.path).toBe('/api/v1/comments/c-1'));
  });

  it('mentions a person picked from the bank, sends their id beside the text, and names who was not notified', async () => {
    const posted = comment('c-9', { author: SARA, body: 'Please check, Johan Berg ', mentions: [JOHAN] });
    let thread = [comment('c-1')];
    const sent = serve([], (s) => {
      if (s.path === '/api/v1/comments' && s.method === 'get') return { status: 200, data: { items: thread, total: thread.length } };
      if (s.method === 'post') {
        thread = [...thread, posted];
        return { status: 201, data: { ...posted, undeliveredMentions: [JOHAN] } };
      }
      return undefined;
    });
    renderIn(<CommentsPanel subject={SUBJECT} />);

    const box = await screen.findByRole('combobox', { name: 'Add a comment' });
    expect(screen.getByRole('button', { name: 'Comment' })).toBeDisabled();
    fireEvent.change(box, { target: { value: 'Please check, @jo', selectionStart: 17 } });
    const option = await screen.findByRole('option', { name: 'Johan Berg' });
    expect(box).toHaveAttribute('aria-expanded', 'true');
    expect(box).toHaveAttribute('aria-activedescendant', option.id);
    expect(screen.queryByRole('option', { name: 'Sara Lind' })).toBeNull();
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(box).toHaveValue('Please check, Johan Berg ');
    expect(box).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Comment' }));
    await waitFor(() => expect(box).toHaveValue(''));
    expect(sent.find((s) => s.method === 'post')?.body).toEqual({ ...SUBJECT, body: 'Please check, Johan Berg ', mentionUserIds: ['u-2'] });
    await waitFor(() => expect(within(rowOf('c-9')).getByText('Not notified: Johan Berg.')).toBeInTheDocument());
    // The mention reads as the name at 500, with no "@".
    expect(within(rowOf('c-9')).getByText('Johan Berg', { selector: 'span.font-medium' })).toBeInTheDocument();
  });

  it('says when nobody matches the letters typed, and closes the list on Escape', async () => {
    serve([]);
    renderIn(<CommentsPanel subject={SUBJECT} />);

    const box = await screen.findByRole('combobox', { name: 'Add a comment' });
    fireEvent.change(box, { target: { value: '@zz', selectionStart: 3 } });
    expect(await screen.findByText("No one in your organisation matches 'zz'")).toBeInTheDocument();
    fireEvent.keyDown(box, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('keeps the text and says so when the post does not reach the server', async () => {
    installAdapter((s) => {
      if (s.path === '/api/v1/me') return { status: 200, data: ME };
      if (s.method === 'get') return { status: 200, data: { items: [], total: 0 } };
      throw new AxiosError('Network Error', 'ERR_NETWORK');
    });
    renderIn(<CommentsPanel subject={SUBJECT} />);

    const box = await screen.findByRole('combobox', { name: 'Add a comment' });
    fireEvent.change(box, { target: { value: 'Draft', selectionStart: 5 } });
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }));
    expect(await screen.findByText('Could not post. Check your connection and try again.')).toBeInTheDocument();
    expect(box).toHaveValue('Draft');
  });

  it('reads without a composer for a reader who may not comment', async () => {
    serve([comment('c-1')]);
    renderIn(<CommentsPanel subject={SUBJECT} />, []);

    expect(await screen.findByText('You can read comments here but not add them.')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('shows the empty line with the composer below it', async () => {
    serve([]);
    renderIn(<CommentsPanel subject={SUBJECT} />);

    expect(await screen.findByText('No comments yet')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Add a comment' })).toBeInTheDocument();
  });

  it('shows skeletons while loading, then an error with Try again and no composer', async () => {
    let fail = true;
    serve([comment('c-1')], (s) => (s.path === '/api/v1/comments' && fail ? { status: 500 } : undefined));
    renderIn(<CommentsPanel subject={SUBJECT} />);

    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(await screen.findByText('Could not load the comments. Check your connection and try again.')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).toBeNull();
    fail = false;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Body of c-1')).toBeInTheDocument();
  });

  it('loads newer comments with Show more', async () => {
    const sent = serve([], (s) => {
      if (s.path !== '/api/v1/comments') return undefined;
      const offset = (s.params as { offset: number }).offset;
      return { status: 200, data: { items: offset === 0 ? [comment('c-1')] : [comment('c-2')], total: 2 } };
    });
    renderIn(<CommentsPanel subject={SUBJECT} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Show more' }));
    expect(await screen.findByText('Body of c-2')).toBeInTheDocument();
    expect(sent.filter((s) => s.path === '/api/v1/comments').map((s) => (s.params as { offset: number }).offset)).toEqual([0, 1]);
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull();
  });
});

describe('the obligation page and the change page', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  const workflow = { change: {}, workflow: { id: 'case-1' } } as unknown as CasePanelProps;
  const reads = (sent: Sent[]) => sent.filter((s) => s.path === '/api/v1/comments').map((s) => s.params);

  it('mount the same comments panel, on the obligation and on the bank’s case', async () => {
    const sent = serve([]);
    renderIn(
      <>
        <ObligationCommentsPanel obligationId="ob-1" />
        <ChangeCommentsPanel {...workflow} />
      </>,
      ['comments.write', 'cases.read'],
    );

    await waitFor(() => expect(screen.getAllByText('No comments yet')).toHaveLength(2));
    // The attribute is CommentsPanel's own: both pages render that one component.
    expect([...document.querySelectorAll('[data-comments-panel]')].map((el) => el.getAttribute('data-comments-panel'))).toEqual(['obligation', 'change_case']);
    expect(reads(sent)).toEqual([
      { subjectType: 'obligation', subjectId: 'ob-1', limit: 20, offset: 0 },
      { subjectType: 'change_case', subjectId: 'case-1', limit: 20, offset: 0 },
    ]);
  });

  it('shows no case comments to a reader whose role cannot read cases', async () => {
    const sent = serve([]);
    renderIn(<ChangeCommentsPanel {...workflow} />, ['comments.write']);

    await waitFor(() => expect(sent.some((s) => s.path === '/api/v1/me')).toBe(false));
    expect(document.querySelector('[data-comments-panel]')).toBeNull();
    expect(reads(sent)).toEqual([]);
  });
});
