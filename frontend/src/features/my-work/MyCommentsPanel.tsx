'use client';

import Link from 'next/link';
import { useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/Button';
import { Tabs, TabPanel } from '@/components/ui/Tabs';
import { formatCollabTime, permissionLimitedLines } from '@/features/collab/collab-presentation';
import { useMyComments } from '@/features/collab/hooks';
import type { MyComment, MyCommentsAbout } from '@/features/collab/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

import { myCommentHref } from './my-work-presentation';

// My work's "Comments and mentions" (COL-01, COL-S12; tenant-my-work.html §6,
// design/system/comments-and-mentions.md). Mentions and My comments from
// GET /me/comments, newest first, 20 a page. Each row links to its record,
// where the record's own comments panel and composer are: a comment is always
// written on its record, so this panel has no composer of its own. A kind the
// reader's role cannot open is named in one line, never a record.

const DOT = "before:mx-1.5 before:content-['·']";

function CommentRow({ comment, about, now }: { comment: MyComment; about: MyCommentsAbout; now: Date }) {
  const t = useT();
  const ctx = useFormatContext();
  const href = myCommentHref(comment);
  const time = formatCollabTime(comment.createdAt, now, ctx, t);
  return (
    <li className="border-b border-line py-2.5 last:border-b-0" data-my-comment={comment.id}>
      <h3>
        {href === null ? (
          comment.subjectTitle
        ) : (
          <Link href={href} prefetch={false} className="no-underline hover:underline">
            {comment.subjectTitle}
          </Link>
        )}
      </h3>
      <p className="mt-0.5 text-meta text-muted">
        {about === 'mentioned' ? (
          <>
            <span>{t('collab.comments.mentionedYou', { name: comment.author.name })}</span>
            <span className={DOT}>{time}</span>
          </>
        ) : (
          <span>{time}</span>
        )}
      </p>
    </li>
  );
}

export function MyCommentsPanel() {
  const t = useT();
  const [about, setAbout] = useState<MyCommentsAbout>('mentioned');
  const query = useMyComments(about);
  const now = new Date();
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const limited = permissionLimitedLines(query.data?.pages[0]?.permissionLimitedKinds ?? [], t);

  let content: ReactNode;
  if (query.isPending) {
    content = (
      <div role="status" aria-busy="true" className="grid gap-2">
        <span className="sr-only">{t('common.loading')}</span>
        {[0, 1].map((i) => (
          <div key={i} className="h-12 rounded-card bg-subtle" aria-hidden="true" />
        ))}
      </div>
    );
  } else if (query.isError) {
    content = (
      <div role="alert" className="flex flex-wrap items-center gap-2">
        <span className="text-muted">{t('collab.comments.loadFailed')}</span>
        <Button variant="outline" size="small" onClick={() => void query.refetch()}>
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
          <ol className="list-none">
            {items.map((comment) => (
              <CommentRow key={comment.id} comment={comment} about={about} now={now} />
            ))}
          </ol>
        )}
        {limited.map((line) => (
          <p key={line} className="mt-2.5 text-meta text-muted" data-permission-limited="">
            {line}
          </p>
        ))}
        {query.hasNextPage ? (
          <Button variant="outline" size="small" className="mt-3" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {t('collab.comments.showMore')}
          </Button>
        ) : null}
      </>
    );
  }

  return (
    <section className="rounded-card border border-line bg-surface p-4" data-my-comments-panel="">
      <h2 className="mb-3">{t('collab.comments.myWorkTitle')}</h2>
      <Tabs
        tabs={[
          { id: 'mentioned', label: t('collab.comments.tabMentions') },
          { id: 'written', label: t('collab.comments.tabWritten') },
        ]}
        current={about}
        onSelect={(id) => setAbout(id === 'written' ? 'written' : 'mentioned')}
      />
      <TabPanel id={about}>{content}</TabPanel>
    </section>
  );
}
