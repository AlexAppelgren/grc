'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { presentCalendarFeed } from '@/features/calendar-feeds/calendar-feeds-presentation';
import { useCalendarFeeds, useCreateCalendarFeed, useRevokeCalendarFeed } from '@/features/calendar-feeds/hooks';
import type { CalendarFeed, CalendarFeedCreated } from '@/features/calendar-feeds/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// My calendar feeds (design/screens/tenant-calendar-feeds.html, HOM-04,
// D-52, ADR 0045): a person's own, revocable addresses onto their bank's
// roadmap. A subscription's body names no field (D-52 removed the
// "Include" choice: every feed carries the same public dates, so there is
// nothing to choose), so "Subscribe" mints one on the spot; creating asks
// for a recent sign-in or a passkey, which the api client's step-up prompt
// drives off the server's own `step_up_required` and retries once.
//
// The address exists in this component's state for the one render and
// reaches no storage, no URL and no log line: it is shown once, straight
// after creation, and there is no way to ask for it again.

function NewFeedPanel({ created, onDone }: { created: CalendarFeedCreated; onDone: () => void }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(created.url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Panel title={t('calendarFeeds.newFeedTitle')} role="status" data-new-feed="">
      <pre className="m-0 mb-3 rounded-control border border-line bg-subtle p-3 font-mono whitespace-pre-wrap break-all" data-feed-address="">
        {created.url}
      </pre>
      <p className="text-muted">{t('calendarFeeds.newFeedBody')}</p>
      <p className="text-meta text-muted">{t('calendarFeeds.newFeedOnce')}</p>
      {copied ? <StatusLine tone="positive">{t('calendarFeeds.copied')}</StatusLine> : null}
      <ButtonBar>
        <Button variant="outline" size="small" onClick={onDone}>
          {t('common.done')}
        </Button>
        <Button size="small" onClick={() => void copy()}>
          {t('calendarFeeds.copy')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

function RevokeFeedModal({ open, pending, onClose, onConfirm }: { open: boolean; pending: boolean; onClose: () => void; onConfirm: () => void }) {
  const t = useT();
  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={t('calendarFeeds.revokeTitle')} description={t('calendarFeeds.revokeBody')}>
      <ButtonBar>
        <Button variant="outline" onClick={onClose} disabled={pending}>
          {t('common.cancel')}
        </Button>
        <Button variant="danger" disabled={pending} onClick={onConfirm}>
          {t('calendarFeeds.revokeAction')}
        </Button>
      </ButtonBar>
    </Modal>
  );
}

function FeedRow({ feed }: { feed: CalendarFeed }) {
  const t = useT();
  const ctx = useFormatContext();
  const revoke = useRevokeCalendarFeed();
  const [confirming, setConfirming] = useState(false);
  const live = feed.revokedAt === null;
  return (
    <Row data-feed-id={feed.id}>
      <Meta>
        <PillRow pills={presentCalendarFeed(feed, t)} />
        <span>{t('calendarFeeds.created', { date: formatDateTime(feed.createdAt, ctx) })}</span>
        <span>{feed.lastUsedAt === null ? t('calendarFeeds.neverFetched') : t('calendarFeeds.lastUsed', { date: formatDateTime(feed.lastUsedAt, ctx) })}</span>
        {feed.revokedAt !== null ? <span>{t('calendarFeeds.revokedOn', { date: formatDateTime(feed.revokedAt, ctx) })}</span> : null}
      </Meta>
      {revoke.isError ? <ProblemAlert error={revoke.error} /> : null}
      {live ? (
        <ButtonBar>
          <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
            {t('calendarFeeds.revoke')}
          </Button>
        </ButtonBar>
      ) : null}
      <RevokeFeedModal
        open={confirming}
        pending={revoke.isPending}
        onClose={() => setConfirming(false)}
        onConfirm={() => revoke.mutate(feed.id, { onSuccess: () => setConfirming(false) })}
      />
    </Row>
  );
}

export function CalendarFeedsScreen() {
  const t = useT();
  const feeds = useCalendarFeeds();
  const create = useCreateCalendarFeed();
  const [created, setCreated] = useState<CalendarFeedCreated | null>(null);

  return (
    <>
      <PageHead
        title={t('calendarFeeds.title')}
        lede={t('calendarFeeds.lede')}
        actions={
          <Button onClick={() => create.mutate(undefined, { onSuccess: (feed) => setCreated(feed) })} disabled={create.isPending}>
            {t('calendarFeeds.subscribe')}
          </Button>
        }
      />
      <p className="mb-5 max-w-[72ch] text-meta text-muted">{t('calendarFeeds.about')}</p>
      {create.isError ? <ProblemAlert error={create.error} codes={{ step_up_required: t('problem.stepUpCancelled') }} /> : null}
      {created !== null ? <NewFeedPanel created={created} onDone={() => setCreated(null)} /> : null}
      {feeds.isPending ? (
        <LoadingState />
      ) : feeds.isError ? (
        <ErrorState title={t('calendarFeeds.errorTitle')} onRetry={() => void feeds.refetch()} />
      ) : feeds.data.length === 0 ? (
        <EmptyState title={t('calendarFeeds.emptyTitle')} body={t('calendarFeeds.emptyBody')} />
      ) : (
        <Rows data-feeds-list="">
          {feeds.data.map((feed) => (
            <FeedRow key={feed.id} feed={feed} />
          ))}
        </Rows>
      )}
    </>
  );
}
