'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';

import { PRIVATE_QUEUE_PAGE as PAGE } from './api';
import { usePrivateProposals } from './hooks';
import { presentPrivateProposal, proposerLine, sourceHost } from './private-record-presentation';
import type { PrivateProposalRow } from './types';

// /private-records (design/screens/tenant-private-records.html; OWN-03, PRO-03, INV-07).
// The bank's own queue: what its own agent or a colleague proposed as a record of the
// bank's own, oldest first, the order the work arrived in, a page of 20 at a time with
// the API's own `total`. The route answers every status in one list, so the status is
// the row's pill rather than a tab. Nothing here names or waits for a platform reviewer.

function QueueRow({ row }: { row: PrivateProposalRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const proposer = proposerLine(row, t);
  const host = sourceHost(row.sourceUrl ?? '');
  return (
    <Link
      href={`/private-records/${row.id}`}
      prefetch={false}
      data-private-proposal-id={row.id}
      data-private-proposal-status={row.status}
      className="block rounded-card border border-line bg-surface px-4 py-3 hover:border-fg"
    >
      <PillRow pills={presentPrivateProposal(row, t)} />
      <h3 className="my-1.5 font-medium">{row.title}</h3>
      <p className="flex flex-wrap gap-x-3 gap-y-1 text-meta text-muted">
        {proposer !== null ? <span>{proposer}</span> : null}
        <span>{formatDateTime(row.createdAt, ctx)}</span>
        {host !== null ? <span>{t('privateRecords.source', { host })}</span> : null}
      </p>
    </Link>
  );
}

export function PrivateRecordsScreen() {
  const t = useT();
  const [offset, setOffset] = useState(0);
  const query = usePrivateProposals(offset);
  const forbidden = forbiddenFrom(query.error);

  let body;
  if (query.isPending) body = <LoadingState rows={3} />;
  else if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  else if (query.isError) body = <ErrorState title={t('privateRecords.loadError')} onRetry={() => void query.refetch()} />;
  else if (query.data.items.length === 0 && offset === 0) {
    body = <EmptyState title={t('privateRecords.empty.title')} body={t('privateRecords.empty.body')} action={{ label: t('privateRecords.empty.action'), href: '/admin/footprint' }} />;
  } else {
    const { items, total } = query.data;
    body = (
      <>
        <div className="grid gap-2" data-private-proposals="">
          {items.map((row) => (
            <QueueRow key={row.id} row={row} />
          ))}
        </div>
        {total > PAGE ? (
          <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
            <span className="text-meta text-muted">{t('privateRecords.range', { from: offset + 1, to: offset + items.length, total })}</span>
            <ButtonBar className="mt-0">
              <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                {t('privateRecords.previous')}
              </Button>
              <Button variant="outline" size="small" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
                {t('privateRecords.next')}
              </Button>
            </ButtonBar>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <div data-private-records="">
      <PageHead title={t('privateRecords.title')} lede={t('privateRecords.lede')} />
      {body}
    </div>
  );
}
