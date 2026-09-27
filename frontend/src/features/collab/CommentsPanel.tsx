'use client';

import { useId, useState, type FormEvent, type ReactNode } from 'react';

import { Button } from '@/components/ui/Button';
import { TextArea } from '@/components/ui/Field';
import { ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { NETWORK_PROBLEM_CODE } from '@/shared/utils/problem';

import { notNotifiedLine, presentComment } from './collab-presentation';
import { useAddComment, useComments, useDeleteComment, useEditComment } from './hooks';
import { MentionPicker } from './MentionPicker';
import type { Comment, CommentCreated, CommentSubject, PersonRef } from './types';

// The one comments panel (COL-01, design/system/comments-and-mentions.md):
// the obligation page and the change page each mount it with their subject.
// Oldest first, 20 a page. Edit and Delete come from the server's
// `canEdit` and `canDelete` for this reader, never from comparing ids or
// from a role. A comment's text is the bank's own: nothing here logs it or
// puts it anywhere but the thread.

const COMMENTS_WRITE = 'comments.write';

// Name, time and "Edited" are joined by a middle dot the stylesheet draws.
const DOT = "text-meta text-muted before:mx-1.5 before:content-['·']";

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** The body as written, each mentioned person's name at 500 with no "@". */
export function bodyWithMentions(body: string, mentions: readonly PersonRef[]): ReactNode[] {
  const names = [...new Set(mentions.map((p) => p.name))].filter((n) => n !== '').sort((a, b) => b.length - a.length);
  if (names.length === 0) return [body];
  // A capturing split puts every matched name at an odd index.
  return body.split(new RegExp(`(${names.map(escapeRegExp).join('|')})`)).map((part, i) =>
    i % 2 === 1 ? (
      <span key={i} className="font-medium">
        {part}
      </span>
    ) : (
      part
    ),
  );
}

export function CommentsPanel({ subject }: { subject: CommentSubject }) {
  const t = useT();
  const comments = useComments(subject);
  const canWrite = (usePermissions() ?? []).includes(COMMENTS_WRITE);
  // "Not notified: …" belongs to the author's own new comment, once: a reload drops it.
  const [undelivered, setUndelivered] = useState<{ commentId: string; line: string } | null>(null);

  const items = comments.data?.pages.flatMap((page) => page.items) ?? [];
  const total = comments.data?.pages[0]?.total;

  function onPosted(created: CommentCreated) {
    const line = notNotifiedLine(created.undeliveredMentions, t);
    setUndelivered(line === null ? null : { commentId: created.id, line });
  }

  let content: ReactNode;
  if (comments.isPending) {
    content = (
      <div role="status" aria-busy="true" className="grid gap-2">
        <span className="sr-only">{t('common.loading')}</span>
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-12 rounded-card bg-subtle" aria-hidden="true" />
        ))}
      </div>
    );
  } else if (comments.isError) {
    content = (
      <div role="alert" className="flex flex-wrap items-center gap-2">
        <span className="text-muted">{t('collab.comments.loadFailed')}</span>
        <Button variant="outline" size="small" onClick={() => void comments.refetch()}>
          {t('collab.comments.tryAgain')}
        </Button>
      </div>
    );
  } else {
    content = (
      <>
        {items.length === 0 ? (
          <p className="text-muted">{t('collab.comments.empty')}</p>
        ) : (
          <ol className="grid list-none gap-4" data-comment-list="">
            {items.map((comment) => (
              <CommentItem key={comment.id} comment={comment} undelivered={undelivered?.commentId === comment.id ? undelivered.line : null} />
            ))}
          </ol>
        )}
        {comments.hasNextPage ? (
          <Button variant="outline" size="small" className="mt-3" disabled={comments.isFetchingNextPage} onClick={() => void comments.fetchNextPage()}>
            {t('collab.comments.showMore')}
          </Button>
        ) : null}
        {canWrite ? <Composer subject={subject} onPosted={onPosted} /> : <p className="mt-4 text-muted">{t('collab.comments.readOnly')}</p>}
      </>
    );
  }

  return (
    <section className="mb-4 rounded-card border border-line bg-surface p-4" data-comments-panel={subject.subjectType}>
      <h2 className="mb-3">
        {t('collab.comments.title')}
        {total === undefined ? null : <span className="ml-2 text-meta font-normal text-muted">{total}</span>}
      </h2>
      {content}
    </section>
  );
}

type Mode = 'view' | 'edit' | 'delete';

function CommentItem({ comment, undelivered }: { comment: Comment; undelivered: string | null }) {
  const t = useT();
  const ctx = useFormatContext();
  const shown = presentComment(comment, new Date(), ctx, t);
  const [mode, setMode] = useState<Mode>('view');
  const [draft, setDraft] = useState('');
  const edit = useEditComment();
  const remove = useDeleteComment();
  const editId = useId();

  function startEdit() {
    edit.reset();
    setDraft(comment.body ?? '');
    setMode('edit');
  }

  function save(e: FormEvent) {
    e.preventDefault();
    edit.mutate({ commentId: comment.id, body: { body: draft } }, { onSuccess: () => setMode('view') });
  }

  const buttons =
    mode === 'view' && shown.deleted === null && (comment.canEdit || comment.canDelete) ? (
      <div className="order-3 ml-auto flex gap-1 md:order-2">
        {comment.canEdit ? (
          <Button variant="ghost" size="small" onClick={startEdit}>
            {t('collab.comments.edit')}
          </Button>
        ) : null}
        {comment.canDelete ? (
          <Button
            variant="ghost"
            size="small"
            onClick={() => {
              remove.reset();
              setMode('delete');
            }}
          >
            {t('collab.comments.delete')}
          </Button>
        ) : null}
      </div>
    ) : null;

  let body: ReactNode;
  if (shown.deleted !== null) {
    body = <p className="text-muted italic">{shown.deleted}</p>;
  } else if (mode === 'edit') {
    body = (
      <form onSubmit={save} className="grid gap-2">
        <TextArea id={editId} aria-label={t('collab.comments.edit')} className="field-sizing-content" value={draft} autoFocus onChange={(e) => setDraft(e.target.value)} />
        <ProblemAlert error={edit.error} codes={{ edit_window_closed: t('collab.comments.editClosed'), [NETWORK_PROBLEM_CODE]: t('collab.comments.postFailed') }} />
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="small" onClick={() => setMode('view')}>
            {t('collab.comments.cancel')}
          </Button>
          <Button type="submit" size="small" disabled={draft.trim() === '' || edit.isPending}>
            {t('collab.comments.save')}
          </Button>
        </div>
      </form>
    );
  } else {
    body = <p className="max-w-[70ch] whitespace-pre-wrap">{bodyWithMentions(comment.body ?? '', comment.mentions)}</p>;
  }

  return (
    <li data-comment-id={comment.id}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <p className="order-1 m-0 min-w-0 basis-full md:flex-1 md:basis-auto">
          <span className="font-medium">{shown.author}</span>
          <span className={DOT}>{shown.time}</span>
          {shown.edited === null ? null : <span className={DOT}>{shown.edited}</span>}
        </p>
        {buttons}
        <div className="order-2 basis-full md:order-3">{body}</div>
      </div>
      {mode === 'delete' ? (
        <div role="group" aria-label={t('collab.comments.deleteConfirm')} className="mt-2 flex flex-wrap items-center justify-end gap-2">
          <span className="mr-auto">{t('collab.comments.deleteConfirm')}</span>
          <Button variant="outline" size="small" onClick={() => setMode('view')}>
            {t('collab.comments.cancel')}
          </Button>
          <Button variant="danger" size="small" disabled={remove.isPending} onClick={() => remove.mutate(comment.id, { onSuccess: () => setMode('view') })}>
            {t('collab.comments.delete')}
          </Button>
          <ProblemAlert error={remove.error} className="basis-full text-right text-meta text-negative" />
        </div>
      ) : null}
      {undelivered === null ? null : <p className="mt-1 text-meta text-muted" data-not-notified="">{undelivered}</p>}
    </li>
  );
}

function Composer({ subject, onPosted }: { subject: CommentSubject; onPosted: (created: CommentCreated) => void }) {
  const t = useT();
  const id = useId();
  const add = useAddComment();
  const [body, setBody] = useState('');
  const [picked, setPicked] = useState<PersonRef[]>([]);

  function submit(e: FormEvent) {
    e.preventDefault();
    // A person counts as mentioned while their name is still in the text.
    const mentionUserIds = [...new Set(picked.filter((p) => body.includes(p.name)).map((p) => p.id))];
    add.mutate(
      { ...subject, body, mentionUserIds },
      {
        onSuccess: (created) => {
          setBody('');
          setPicked([]);
          onPosted(created);
          document.getElementById(id)?.focus();
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="mt-4 grid gap-1.5" data-comment-composer="">
      <label htmlFor={id} className="font-medium">
        {t('collab.comments.addLabel')}
      </label>
      <MentionPicker
        id={id}
        aria-describedby={`${id}-hint`}
        value={body}
        onValueChange={setBody}
        onPick={(person) => setPicked((people) => [...people, person])}
      />
      <span id={`${id}-hint`} className="text-meta text-muted" data-visibility-line="">
        {t('collab.comments.visibility')}
      </span>
      <ProblemAlert error={add.error} className="text-meta text-negative" codes={{ [NETWORK_PROBLEM_CODE]: t('collab.comments.postFailed') }} />
      <div className="flex justify-end">
        <Button type="submit" size="small" disabled={body.trim() === '' || add.isPending}>
          {t('collab.comments.submit')}
        </Button>
      </div>
    </form>
  );
}
