import { Notice } from '@/components/ui/Notice';
import { PillRow } from '@/components/ui/PillRow';
import { useFormatContext } from '@/features/identity/hooks';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { ChangeDetail } from '@/features/watch/api';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';

// The documents panel of design/screens/tenant-change.html: every page the
// reform was found on, the primary one first, with merged duplicates marked
// (AC-WAT1) and a screening hit shown as a warning (AGT-07).
//
// The fetched text itself is never in the response and is never rendered:
// a reader gets the address and opens the publisher's own page. Fetched
// content is untrusted, so the title and the publisher render as text and
// nothing here renders HTML.

export type ChangeDocument = ChangeDetail['documents'][number];

/** A document's pills: only "merged as duplicate", whose tone is the slot's. */
export function presentDocument(document: ChangeDocument, t: Translate): PresentedPill[] {
  if (!document.isDuplicate) return [];
  return [{ key: `duplicate:${document.id}`, label: t('watch.change.mergedDuplicate'), tone: slotTone.duplicate, order: 10 }];
}

/** "Finansinspektionen, fetched 16 Sep 2026 06:58", or the fetch alone when the page names no publisher. */
export function fetchedLine(document: ChangeDocument, t: Translate, ctx: FormatContext): string | null {
  if (document.fetchedAt === null) return document.publisher;
  const date = formatDateTime(document.fetchedAt, ctx);
  return t('watch.change.fetched', { publisher: document.publisher ?? document.url, date });
}

export function ChangeDocuments({ documents }: { documents: readonly ChangeDocument[] }) {
  const t = useT();
  const ctx = useFormatContext();
  if (documents.length === 0) return <p className="text-meta text-muted">{t('watch.change.noDocuments')}</p>;
  return (
    <div className="text-meta" data-change-documents="">
      {documents.map((document) => (
        <div key={document.id} className="border-b border-line py-2.5 last:border-b-0" data-document={document.id}>
          {fetchedLine(document, t, ctx) !== null ? <span className="block text-muted">{fetchedLine(document, t, ctx)}</span> : null}
          <a href={document.url} rel="noopener noreferrer" target="_blank" className="font-medium underline">
            {document.title ?? document.url}
          </a>
          <PillRow pills={presentDocument(document, t)} />
          {document.riskFlags.length > 0 ? (
            <Notice tone="warn" className="mt-2 mb-0" data-screened="">
              {t('watch.change.screened')}
            </Notice>
          ) : null}
        </div>
      ))}
    </div>
  );
}
