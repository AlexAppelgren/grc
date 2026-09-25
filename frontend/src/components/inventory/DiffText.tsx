'use client';

import { Fragment } from 'react';

import { useT } from '@/shared/i18n/LocaleProvider';

// "Show what changed" (design/screens/tenant-obligation.html; INV-04, AC-INV1):
// the server's sentence-level diff as running text. An added sentence is an
// ins on positive-soft, a removed one a del on negative-soft, both in the
// text colour: the tone's own text on its -02 step fails AA in dark
// (negative 4.47:1), the text colour passes in both themes (contrast.test.ts).
// Screen readers do not announce ins and del, so each says in words where it
// starts and ends.

export interface DiffSegment {
  op: 'equal' | 'insert' | 'delete';
  text: string;
}

const MARKS = {
  insert: { Tag: 'ins', className: 'bg-positive-soft no-underline', start: 'diff.addedStart', end: 'diff.addedEnd' },
  delete: { Tag: 'del', className: 'bg-negative-soft', start: 'diff.removedStart', end: 'diff.removedEnd' },
} as const;

export function DiffText({ segments }: { segments: readonly DiffSegment[] }) {
  const t = useT();
  return (
    <>
      {segments.map((segment, i) => {
        const mark = segment.op === 'equal' ? null : MARKS[segment.op];
        return (
          <Fragment key={i}>
            {i > 0 ? ' ' : null}
            {mark === null ? (
              segment.text
            ) : (
              <mark.Tag className={`rounded-[3px] px-[3px] py-px text-fg ${mark.className}`}>
                <span className="sr-only">{t(mark.start)} </span>
                {segment.text}
                <span className="sr-only"> {t(mark.end)}</span>
              </mark.Tag>
            )}
          </Fragment>
        );
      })}
    </>
  );
}
