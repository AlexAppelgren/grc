'use client';

import Link from 'next/link';
import { Fragment } from 'react';

import { PillRow } from '@/components/ui/PillRow';
import { highlightSnippet, presentSearchHitRow, validityMeta, versionMeta } from '@/features/search/search-presentation';
import type { SearchHit } from '@/features/search/types';
import type { Translate } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';

// One hit of the inventory's search (design/screens/tenant-search.html's hit row,
// D-9x): the pills of its slots, the title, the snippet with the query's words
// marked, and its version and validity. The inventory searches obligations and
// provisions only; watch changes are found on Watch.

const ROW_CLASS = 'block rounded-card border border-line bg-surface px-4 py-3.5';

export function SearchHitRow({ hit, query, t, ctx }: { hit: SearchHit; query: string; t: Translate; ctx: FormatContext }) {
  const segments = highlightSnippet(hit.snippet, query);
  const meta = [versionMeta(hit, t), validityMeta(hit, t, ctx)].filter((line): line is string => line !== null);

  const content = (
    <>
      <PillRow pills={presentSearchHitRow(hit, t)} />
      <h3 className="my-1.5 font-semibold">{hit.title}</h3>
      <p className="text-meta text-muted">
        {segments.map((segment, index) =>
          segment.matched ? (
            <mark key={index} className="rounded-[3px] bg-neutral-soft px-0.5 text-fg">
              {segment.text}
            </mark>
          ) : (
            <Fragment key={index}>{segment.text}</Fragment>
          ),
        )}
      </p>
      {meta.length > 0 ? (
        <p className="mt-1 flex flex-wrap gap-x-2.5 text-meta text-muted">
          {meta.map((line, index) => (
            <span key={index}>{line}</span>
          ))}
        </p>
      ) : null}
    </>
  );

  if (hit.type === 'obligation') {
    return (
      <Link href={`/inventory/obligations/${hit.id}`} prefetch={false} data-hit-type="obligation" className={`${ROW_CLASS} hover:border-fg`}>
        {content}
      </Link>
    );
  }
  // A provision has no screen of its own (INV-03..06 open the obligation, never a
  // provision directly), so it renders as a fact rather than a broken link.
  return (
    <div data-hit-type="provision" className={ROW_CLASS}>
      {content}
    </div>
  );
}
