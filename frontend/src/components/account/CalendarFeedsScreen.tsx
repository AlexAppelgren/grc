'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { presentCalendarFeed } from '@/features/calendar-feeds/calendar-feeds-presentation';
import { useCalendarFeeds, useCreateCalendarFeed, useRevokeCalendarFeed } from '@/features/calendar-feeds/hooks';
import type { CalendarFeed } from '@/features/calendar-feeds/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';

// Calendar feeds (design/screens/tenant-calendar-feeds.html; HOM-04, D-52,
// ADR 0045): a person's own revocable addresses onto the roadmap. "New feed"
// has nothing to fill in, because every feed carries the same public dates.
// Creating one needs a recent sign-in or a passkey, which the api client's
// step-up prompt asks for off the server's `step_up_required` and retries.
//
// The address lives only in the create mutation's answer, which the dialog
// reads and `reset()` drops (the hook keeps no cache of it). It reaches no
// storage, no URL and no log line, and nothing can ask for it again.

function AddressDialog({ url, onDone }: { url: string; onDone: () => void }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Modal open onOpenChange={(next) => (next ? undefined : onDone())} title={t('calendarFeeds.addressTitle')} description={t('calendarFeeds.addressBody')}>
      <pre className="m-0 rounded-control border border-line bg-subtle p-3 font-mono break-all whitespace-pre-wrap" data-feed-address="">
        {url}
      </pre>
      {copied ? <StatusLine tone="positive">{t('calendarFeeds.copied')}</StatusLine> : null}
      <ButtonBar>
        <Button variant="outline" onClick={onDone}>
          {t('common.done')}
        </Button>
        <Button onClick={() => void copy()}>{t('calendarFeeds.copy')}</Button>
      </ButtonBar>
    </Modal>
  );
}

function FeedRow({ feed }: { feed: CalendarFeed }) {
  const t = useT();
  const ctx = useFormatContext();
  const revoke = useRevokeCalendarFeed();
  const [confirming, setConfirming] = useState(false);
  const close = () => {
    setConfirming(false);
    revoke.reset();
  };
  return (
    <Row data-feed-id={feed.id}>
      <Meta>
        <PillRow pills={presentCalendarFeed(feed, t)} />
        <span>{t('calendarFeeds.created', { date: formatDateTime(feed.createdAt, ctx) })}</span>
        <span>{feed.lastUsedAt === null ? t('calendarFeeds.neverFetched') : t('calendarFeeds.lastFetched', { date: formatDateTime(feed.lastUsedAt, ctx) })}</span>
        {feed.revokedAt !== null ? <span>{t('calendarFeeds.revokedOn', { date: formatDateTime(feed.revokedAt, ctx) })}</span> : null}
      </Meta>
      {feed.revokedAt === null ? (
        <ButtonBar>
          <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
            {t('calendarFeeds.revoke')}
          </Button>
        </ButtonBar>
      ) : null}
      <Modal open={confirming} onOpenChange={(next) => (next ? undefined : close())} title={t('calendarFeeds.revokeTitle')} description={t('calendarFeeds.revokeBody')}>
        {revoke.isError ? <ProblemAlert error={revoke.error} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={close} disabled={revoke.isPending}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" disabled={revoke.isPending} onClick={() => revoke.mutate(feed.id, { onSuccess: close })}>
            {t('calendarFeeds.revoke')}
          </Button>
        </ButtonBar>
      </Modal>
    </Row>
  );
}

export function CalendarFeedsScreen() {
  const t = useT();
  const feeds = useCalendarFeeds();
  const create = useCreateCalendarFeed();
  const forbidden = forbiddenFrom(feeds.error);

  return (
    <>
      <BackLink href="/roadmap" label={t('nav.roadmap')} />
      <PageHead
        title={t('calendarFeeds.title')}
        lede={t('calendarFeeds.lede')}
        actions={
          <Button onClick={() => create.mutate()} disabled={create.isPending}>
            {t('calendarFeeds.newFeed')}
          </Button>
        }
      />
      {create.isError ? (
        <ProblemAlert error={create.error} codes={{ step_up_required: t('problem.stepUpCancelled'), feed_limit_reached: t('calendarFeeds.limitReached') }} />
      ) : null}
      {create.data !== undefined ? <AddressDialog url={create.data.url} onDone={() => create.reset()} /> : null}
      {feeds.isPending ? (
        <LoadingState />
      ) : forbidden !== null ? (
        <RestrictedScreen {...forbidden} />
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
