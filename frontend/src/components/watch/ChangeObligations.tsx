import Link from 'next/link';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { CaseObligationDecision, ChangeDetail } from '@/features/watch/api';
import { useAcceptCaseObligationLink, useCanWorkCase, useRemoveCaseObligationLink } from '@/features/watch/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// "Obligations affected" on design/screens/tenant-change.html (WAT-04): the
// duties an agent read the change against, most confident first, each one a
// way into the obligation itself.
//
// Two decisions meet here and stay apart. A link is a library fact:
// `confirmed` says a library editor stood behind it for every bank, and until
// then the confidence the agent recorded is shown as what it is, a
// suggestion. This bank's own decision lives on its case: "Confirm link"
// says the duty really is affected here, "Not related" says it is not, and
// neither moves the library's link or what another bank sees (ruling C). A
// link this bank removed is hidden from this bank's page; it stays stored,
// so the case file can say the bank looked and said no.

export type ObligationLink = ChangeDetail['obligations'][number];

/** This bank's decision per obligation, from its own case. A change it has no case for has decided nothing. */
export function decisionsOf(change: ChangeDetail): Map<string, CaseObligationDecision> {
  return new Map((change.case?.obligationDecisions ?? []).map((decision) => [decision.obligationId, decision]));
}

/**
 * The link's pills: the instrument it belongs to, then whether it is settled.
 * This bank's own confirmation says the most to this reader, so it wins the
 * slot; a library editor's confirmation comes next; otherwise the agent's
 * confidence, as a suggestion.
 */
export function presentObligationLink(link: ObligationLink, decision: CaseObligationDecision | undefined, t: Translate, ctx: FormatContext): PresentedPill[] {
  let settled: PresentedPill;
  if (decision?.decision === 'accepted') {
    settled = {
      key: `accepted:${link.obligationId}`,
      label: t('watch.change.linkAccepted', { date: formatDate(decision.decidedAt, ctx) }),
      tone: slotTone.confirmed,
      order: 20,
    };
  } else if (link.confirmed) {
    settled = { key: `confirmed:${link.obligationId}`, label: t('watch.change.linkConfirmed'), tone: slotTone.confirmed, order: 20 };
  } else {
    settled = {
      key: `suggested:${link.obligationId}`,
      label: link.confidence === null ? t('watch.row.suggestedByAgent') : t('watch.change.matchConfidence', { percent: Math.round(link.confidence * 100) }),
      tone: slotTone.suggested,
      order: 20,
    };
  }
  return [{ key: `instrument:${link.obligationId}`, label: link.instrumentShortName, tone: slotTone.instrument, order: 10 }, settled];
}

export function ChangeObligations({ change }: { change: ChangeDetail }) {
  const t = useT();
  const ctx = useFormatContext();
  const canWork = useCanWorkCase(change);
  const decisions = decisionsOf(change);
  // Every link except those this bank said are not related to it.
  const links = change.obligations.filter((link) => decisions.get(link.obligationId)?.decision !== 'removed');
  if (change.obligations.length === 0) return <p className="text-meta text-muted">{t('watch.change.noObligations')}</p>;
  // The library still links them; this bank said none applies. Saying "nothing
  // is linked" would be untrue, so the page says what the bank decided.
  if (links.length === 0) return <p className="text-meta text-muted">{t('watch.change.allLinksRemoved')}</p>;
  return (
    <Rows data-change-obligations="">
      {links.map((link) => {
        const decision = decisions.get(link.obligationId);
        return (
          <Row key={link.obligationId} data-obligation={link.obligationId} data-case-decision={decision?.decision}>
            <PillRow pills={presentObligationLink(link, decision, t, ctx)} />
            <h3 className="my-1.5 font-semibold">
              <Link href={`/inventory/obligations/${link.obligationId}`} prefetch={false} className="underline">
                {link.title}
              </Link>
            </h3>
            <p className="text-meta text-muted">
              <code className="font-mono">{link.refLabel}</code>
            </p>
            {canWork && decision === undefined ? <LinkDecision changeId={change.id} obligationId={link.obligationId} /> : null}
          </Row>
        );
      })}
    </Rows>
  );
}

/** "Not related" and "Confirm link" for one undecided link, each writing this bank's case alone. */
function LinkDecision({ changeId, obligationId }: { changeId: string; obligationId: string }) {
  const t = useT();
  const accept = useAcceptCaseObligationLink(changeId);
  const remove = useRemoveCaseObligationLink(changeId);
  const pending = accept.isPending || remove.isPending;
  return (
    <>
      {accept.isError ? <ProblemAlert error={accept.error} /> : null}
      {remove.isError ? <ProblemAlert error={remove.error} /> : null}
      <ButtonBar className="mt-2.5">
        <Button variant="ghost" size="small" disabled={pending} onClick={() => remove.mutate(obligationId)}>
          {t('watch.change.notRelated')}
        </Button>
        <Button size="small" disabled={pending} onClick={() => accept.mutate(obligationId)}>
          {t('watch.change.confirmLink')}
        </Button>
      </ButtonBar>
    </>
  );
}
