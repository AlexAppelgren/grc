'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { CONSOLE_CHANGES_PAGE, authorityAndPublished, firstSeen, presentConsoleChange, useConsoleChanges, type ConsoleChangeRow } from '@/features/console-watch/change-facts';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// Change facts (design/screens/console-change-facts.html, WAT-03, WAT-04,
// ADM-02): the queue a library editor works, filtered to the changes still
// carrying a fact nobody has confirmed. It is the console, so a row holds the
// shared library and nothing of a bank's: no case, no footprint verdict, no
// owner and no problem report is read here or anywhere else in the console.
// The filter is the route's own, so a row the server left out never reappears
// because the browser kept it. The card's authority filter is absent rather
// than wrong: `GET /authorities` is gated inside a tenant and refuses a
// console session, and no screen calls a route it cannot pass.

function QueueRow({ row }: { row: ConsoleChangeRow }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-change-id={row.id}>
      <PillRow pills={presentConsoleChange(row, t)} />
      <h3 className="mt-1.5 mb-1 font-semibold">
        <Link href={`/console/change-facts/${row.id}`} className="underline">
          {row.title}
        </Link>
      </h3>
      <Meta>
        <span>{authorityAndPublished(row, t, ctx)}</span>
        <span>{firstSeen(row, t, ctx)}</span>
      </Meta>
    </Row>
  );
}

export function ChangeFactsScreen() {
  const t = useT();
  const [unconfirmedOnly, setUnconfirmedOnly] = useState(true);
  const [offset, setOffset] = useState(0);

  // A changed filter starts again at the first page: the offset of the old
  // result means nothing in the new one.
  const toggleUnconfirmed = () => {
    setUnconfirmedOnly(!unconfirmedOnly);
    setOffset(0);
  };

  const changes = useConsoleChanges({ confirmed: unconfirmedOnly ? 'false' : 'all', limit: CONSOLE_CHANGES_PAGE, offset });

  return (
    <>
      <PageHead title={t('console.changeFacts.title')} lede={t('console.changeFacts.lede')} />
      <Notice>{t('console.changeFacts.explain')}</Notice>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="small" aria-pressed={unconfirmedOnly} onClick={toggleUnconfirmed}>
          {t('console.changeFacts.filter.onlyUnconfirmed')}
        </Button>
      </div>
      {changes.isPending ? (
        <LoadingState rows={3} />
      ) : changes.isError ? (
        <ErrorState title={t('console.changeFacts.errorTitle')} onRetry={() => void changes.refetch()} />
      ) : changes.data.items.length === 0 ? (
        <EmptyState title={t('console.changeFacts.emptyTitle')} body={t('console.changeFacts.emptyBody')} action={{ label: t('console.changeFacts.emptyAction'), href: '/console/sources' }} />
      ) : (
        <>
          <Rows data-change-facts-list="">
            {changes.data.items.map((row) => (
              <QueueRow key={row.id} row={row} />
            ))}
          </Rows>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-meta text-muted">
            <span>{t('console.changeFacts.range', { from: offset + 1, to: offset + changes.data.items.length, total: changes.data.total })}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - CONSOLE_CHANGES_PAGE))}>
                {t('console.changeFacts.newer')}
              </Button>
              <Button variant="outline" size="small" disabled={offset + CONSOLE_CHANGES_PAGE >= changes.data.total} onClick={() => setOffset(offset + CONSOLE_CHANGES_PAGE)}>
                {t('console.changeFacts.older')}
              </Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
