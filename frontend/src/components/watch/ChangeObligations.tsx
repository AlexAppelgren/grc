import Link from 'next/link';

import { Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { ChangeDetail } from '@/features/watch/api';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Obligations affected" on design/screens/tenant-change.html (WAT-04): the
// duties an agent read the change against, most confident first, each one a
// way into the obligation itself.
//
// A link is a library fact: `confirmed` says a library editor stood behind
// it, and until then the confidence the agent recorded is shown as what it
// is, a suggestion. Deciding a link for this bank happens on the bank's own
// case and is not on this panel.

export type ObligationLink = ChangeDetail['obligations'][number];

/** The link's pills: the instrument it belongs to, then whether a person has settled it. */
export function presentObligationLink(link: ObligationLink, t: Translate): PresentedPill[] {
  const settled: PresentedPill = link.confirmed
    ? { key: `confirmed:${link.obligationId}`, label: t('watch.change.linkConfirmed'), tone: slotTone.confirmed, order: 20 }
    : {
        key: `suggested:${link.obligationId}`,
        label:
          link.confidence === null
            ? t('watch.row.suggestedByAgent')
            : t('watch.change.matchConfidence', { percent: Math.round(link.confidence * 100) }),
        tone: slotTone.suggested,
        order: 20,
      };
  return [
    { key: `instrument:${link.obligationId}`, label: link.instrumentShortName, tone: slotTone.instrument, order: 10 },
    settled,
  ];
}

export function ChangeObligations({ obligations }: { obligations: readonly ObligationLink[] }) {
  const t = useT();
  if (obligations.length === 0) return <p className="text-meta text-muted">{t('watch.change.noObligations')}</p>;
  return (
    <Rows data-change-obligations="">
      {obligations.map((link) => (
        <Row key={link.obligationId} data-obligation={link.obligationId}>
          <PillRow pills={presentObligationLink(link, t)} />
          <h3 className="my-1.5 font-semibold">
            <Link href={`/inventory/obligations/${link.obligationId}`} prefetch={false} className="underline">
              {link.title}
            </Link>
          </h3>
          <p className="text-meta text-muted">
            <code className="font-mono">{link.refLabel}</code>
          </p>
        </Row>
      ))}
    </Rows>
  );
}
