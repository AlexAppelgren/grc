'use client';

import Link from 'next/link';

import { EmptyState } from '@/components/ui/EmptyState';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { ChangeRow } from '@/features/watch/api';
import { keyDateMeta, presentChangeRow } from '@/features/watch/change-presentation';
import { useObligationChanges } from '@/features/watch/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import type { Translate } from '@/shared/i18n';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';

// "Related changes" on design/screens/tenant-obligation.html (WAT-04,
// INV-03, INV-06): the reforms an agent read against this duty, and how many
// of them still have work open for this bank.
//
// The read orders them for the screen — the links a library editor confirmed
// first, then the feed's own order — so the panel keeps the order it was
// given rather than sorting a page of twenty for itself. The count is the
// route's own `openCount`, computed over every linked change, so paging can
// never change it and a page of twenty is never counted in the browser.

/** The header's count, a computed pill whose tone comes from its slot. */
export function presentOpenChanges(openCount: number, t: Translate): PresentedPill[] {
  if (openCount === 0) return [];
  return [{ key: 'open-changes', label: t('library.relatedChanges.openCount', { count: openCount }), tone: slotTone.openChanges, order: 10 }];
}

export function RelatedChangeRow({ row, today }: { row: ChangeRow; today: Date }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-related-change={row.stableKey}>
      <PillRow pills={presentChangeRow(row, 'row', t)} />
      <h3 className="my-1.5 font-semibold">
        <Link href={`/watch/${row.id}`} prefetch={false} className="underline">
          {row.title}
        </Link>
      </h3>
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-muted">
        <span>{row.authorityLabel}</span>
        {keyDateMeta(row, t, ctx, today).map((line, index) => (
          // Two facts can read the same, so the position is the key.
          <span key={index}>{line}</span>
        ))}
      </p>
    </Row>
  );
}

export function ObligationRelatedChanges({ obligationId }: { obligationId: string }) {
  const t = useT();
  const query = useObligationChanges(obligationId);
  const forbidden = forbiddenFrom(query.error);
  // One fixed moment for the whole render, so two rows can never disagree
  // about how many days are left.
  const today = new Date();

  return (
    <Panel data-related-changes="">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2>{t('library.relatedChanges.title')}</h2>
        <PillRow pills={presentOpenChanges(query.data?.openCount ?? 0, t)} />
      </div>
      {query.isPending ? (
        <LoadingState rows={2} />
      ) : forbidden !== null ? (
        <RestrictedScreen {...forbidden} />
      ) : query.isError ? (
        <ErrorState title={t('library.relatedChanges.errorTitle')} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title={t('library.relatedChanges.emptyTitle')} body={t('library.relatedChanges.emptyBody')} />
      ) : (
        <>
          <Rows>
            {query.data.items.map((row) => (
              <RelatedChangeRow key={row.id} row={row} today={today} />
            ))}
          </Rows>
          {query.data.total > query.data.items.length ? (
            <p className="mt-3 text-meta text-muted">{t('watch.showing', { shown: query.data.items.length, total: query.data.total })}</p>
          ) : null}
        </>
      )}
    </Panel>
  );
}
