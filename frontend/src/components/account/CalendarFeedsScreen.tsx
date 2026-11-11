'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { SecretOnce } from '@/components/ui/SecretOnce';
import { ConfirmDialog } from '@/components/ui/Dialogs';
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
  // Only Done ends the dialog: Escape or a click outside would drop the one
  // copy of the address and leave a live feed nobody saw.
  return (
    <Modal open onOpenChange={() => undefined} title={t('calendarFeeds.addressTitle')} description={t('calendarFeeds.addressBody')}>
      <SecretOnce secret={url} copyLabel={t('calendarFeeds.copy')} address onDone={onDone} />
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
  // Feeds have no names (D-52), so the created date is what tells one from
  // another, for the row's Revoke button and for the dialog it opens.
  const created = formatDateTime(feed.createdAt, ctx);
  return (
    <Row data-feed-id={feed.id}>
      <Meta>
        <PillRow pills={presentCalendarFeed(feed, t)} />
        <span>{t('calendarFeeds.created', { date: created })}</span>
        <span>{feed.lastUsedAt === null ? t('calendarFeeds.neverFetched') : t('calendarFeeds.lastFetched', { date: formatDateTime(feed.lastUsedAt, ctx) })}</span>
        {feed.revokedAt !== null ? <span>{t('calendarFeeds.revokedOn', { date: formatDateTime(feed.revokedAt, ctx) })}</span> : null}
      </Meta>
      {feed.revokedAt === null ? (
        <ButtonBar>
          <Button variant="danger" size="small" aria-label={t('calendarFeeds.revokeFeed', { date: created })} onClick={() => setConfirming(true)}>
            {t('common.revoke')}
          </Button>
        </ButtonBar>
      ) : null}
      {confirming ? (
        <ConfirmDialog
          title={t('calendarFeeds.revokeTitle', { date: created })}
          body={t('calendarFeeds.revokeBody')}
          action={t('common.revoke')}
          danger
          busy={revoke.isPending}
          error={revoke.error}
          onConfirm={() => revoke.mutate(feed.id, { onSuccess: close })}
          onClose={close}
        />
      ) : null}
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
