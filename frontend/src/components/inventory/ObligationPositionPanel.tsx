'use client';

import { useState, type ReactNode } from 'react';

import { DecideDialog } from '@/components/applies/DecideDialog';
import { APPROVE_PERMISSION, answersOf, type Answer } from '@/components/inventory/ObligationApplicabilityPanel';
import { Facts } from '@/components/inventory/ObligationPanels';
import { EDIT_PERMISSION, EditDialog, standing, type Editing } from '@/components/inventory/ObligationStatusPanel';
import { Button } from '@/components/ui/Button';
import { Fold } from '@/components/ui/fold';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, StatusLine } from '@/components/ui/States';
import { useRefreshAnswers, useSuggestionFacts } from '@/features/applies/hooks';
import { suggestReason } from '@/features/applies/suggestion';
import { useFormatContext } from '@/features/identity/hooks';
import { useObligation } from '@/features/library/hooks';
import { gapKind, REGISTER_READ } from '@/features/register/gaps/gap-view';
import {
  isStaleWrite,
  OBLIGATION_GAPS_PAGE,
  STALE_WRITE_CODE,
  useObligationGaps,
  useRegisterEntry,
  useReloadRegister,
  useSetApplicability,
  useSpannedEntities,
} from '@/features/register/hooks';
import { presentApplicability, presentCompliance } from '@/features/register/register-presentation';
import type { Applicability, RegisterEntityStatus, RegisterEntry } from '@/features/register/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';

// "Our position" (design/screens/tenant-obligation.html; REG-01, REG-02, D-42):
// one block per company the obligation spans, each with "Does it apply" (the
// answer, who set it when, the reason, Decide or Change) and, where it applies,
// "Where we stand" (the status, owner, next review, open gaps, the note, Edit,
// and the rest of that company's facts under "More"). Where it spans one company
// or none, the block is the obligation's own and carries no company heading. A
// standard's units follow the blocks. "Applies" and "we comply" stay two facts:
// each has its own line and its own dialog.

/** One company's block: its answer, and its standing where it applies. `name` is null for the obligation as a whole. */
export interface PositionBlock {
  key: string;
  name: string | null;
  answer: Answer | null;
  standing: RegisterEntityStatus | RegisterEntry | null;
}

/**
 * The blocks in the order the answers come, each with the standing of the
 * company it names. The obligation's own standing is asked only where it is
 * kept as a whole and applies; a company that applies without an answer of its
 * own on show (the obligation spans fewer than two) gets a block of its own, so
 * nothing the register holds goes unseen.
 */
export function positionBlocks(entry: RegisterEntry, spanned: readonly { orgUnitId: string; orgUnitName: string }[]): PositionBlock[] {
  const applying = entry.entities.filter((entity) => entity.applicability === 'applies');
  const wholeStands = entry.entities.length === 0 && entry.applicability === 'applies';
  const blocks: PositionBlock[] = answersOf(entry, spanned).map((answer) => ({
    key: answer.orgUnitId ?? 'whole',
    name: answer.name,
    answer,
    standing: answer.orgUnitId === null ? (wholeStands ? entry : null) : (applying.find((entity) => entity.orgUnitId === answer.orgUnitId) ?? null),
  }));
  for (const entity of applying) {
    if (!blocks.some((block) => block.key === entity.orgUnitId)) blocks.push({ key: entity.orgUnitId, name: entity.orgUnitName, answer: null, standing: entity });
  }
  return blocks;
}

/** "1 open gap" for a company, or for the whole obligation: read only by someone who may read the register. */
function OpenGaps({ obligationId, orgUnitId }: { obligationId: string; orgUnitId: string | null }) {
  const t = useT();
  const gaps = useObligationGaps(obligationId, OBLIGATION_GAPS_PAGE);
  const open = (gaps.data?.items ?? []).filter((gap) => (orgUnitId === null || gap.orgUnitId === orgUnitId) && ['open', 'remediating'].includes(gapKind(gap)));
  return open.length === 0 ? null : <span>{t('obligationStatus.openGaps', { count: open.length })}</span>;
}

/** Nobody has answered this row yet: it reads "Not assessed" with no one's name on it. */
const unanswered = (answer: Answer): boolean => answer.decidedAt === null && answer.applicability === 'under_assessment';

/**
 * One answer set through the dialog "What applies" uses (D-141): one step, with "Not
 * assessed" as a third choice. A company's row nobody answered opens on Applies with the
 * reason suggested from the licence facts, read only now, and so does one stored as "Not
 * assessed"; the obligation as a whole and a row answered either way suggest nothing. A stale write re-reads the register, so the dialog's
 * "Now" line shows what the colleague set and the person's words stay in the field.
 */
function DecideOne({ obligationId, answer, onClose }: { obligationId: string; answer: Answer; onClose: (stored: Applicability | null) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const set = useSetApplicability(obligationId);
  const reload = useReloadRegister();
  const refresh = useRefreshAnswers();
  // A row stored as "Not assessed" is still to decide: the dialog opens it on Applies with the suggestion.
  const toDecide = answer.applicability === 'under_assessment';
  const instrument = useObligation(obligationId).data?.instrument;
  const facts = useSuggestionFacts(answer.orgUnitId ?? '', instrument, toDecide && answer.orgUnitId !== null);
  const suggestion = facts === null || answer.name === null ? '' : suggestReason([facts.basis], answer.name, facts.register, t, ctx);
  return (
    <DecideDialog
      company={answer.orgUnitId === null ? null : answer.name}
      current={unanswered(answer) ? null : { applicability: answer.applicability, reason: answer.reason }}
      notAssessed
      suggestion={suggestion}
      pending={set.isPending}
      error={set.isError ? set.error : undefined}
      codes={{ [STALE_WRITE_CODE]: t('obligationApplicability.stale') }}
      onSubmit={({ applicability, reason }) =>
        set.mutate(
          { body: { applicability, reason, ...(answer.orgUnitId === null ? {} : { orgUnitId: answer.orgUnitId }) }, version: answer.version },
          {
            onSuccess: () => {
              refresh();
              onClose(applicability);
            },
            onError: (error) => {
              if (isStaleWrite(error)) void reload();
            },
          },
        )
      }
      onClose={() => onClose(null)}
    />
  );
}

function ActionRow({ children, action }: { children: ReactNode; action: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">{children}</div>
      {action === null ? null : <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function ObligationPositionPanel({ obligationId, children }: { obligationId: string; children?: ReactNode }) {
  const t = useT();
  const ctx = useFormatContext();
  const permissions = usePermissions() ?? [];
  const canDecide = permissions.includes(APPROVE_PERMISSION);
  const canEdit = permissions.includes(EDIT_PERMISSION);
  const readsGaps = permissions.includes(REGISTER_READ);
  const entry = useRegisterEntry(obligationId);
  const span = useSpannedEntities(obligationId);
  // The block whose answer is being decided, read from the blocks each time, so a re-read brings its version.
  const [deciding, setDeciding] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [decided, setDecided] = useState<Applicability | null>(null);
  const [saved, setSaved] = useState(false);
  const title = t('inventory.obligation.card.position');

  if (entry.isError || span.isError) {
    return (
      <Panel title={title} data-applicability-panel="" data-status-panel="">
        <ErrorState
          title={t('obligationApplicability.errorTitle')}
          onRetry={() => {
            void entry.refetch();
            void span.refetch();
          }}
        />
      </Panel>
    );
  }
  if (entry.data === undefined || span.data === undefined) {
    return (
      <Panel title={title} data-applicability-panel="" data-status-panel="">
        <LoadingState rows={2} />
      </Panel>
    );
  }

  const data = entry.data;
  const blocks = positionBlocks(data, span.data);
  const named = blocks.length > 1;
  const decidingAnswer = blocks.find((block) => block.key === deciding)?.answer ?? null;

  return (
    <Panel title={title} data-applicability-panel="" data-status-panel="">
      {blocks.map((block) => {
        const facts = block.standing === null ? [] : standing(block.standing, t, ctx);
        const fact = (key: string) => facts.find((row) => row.key === key)?.value ?? null;
        const owner = fact('owner');
        const review = fact('review');
        const more = facts.filter((row) => !['note', 'owner', 'review'].includes(row.key));
        const heading = block.name ?? (named ? t('obligationApplicability.whole') : null);
        return (
          <div key={block.key} className="mt-4 border-t border-line pt-4 first-of-type:mt-0 first-of-type:border-t-0 first-of-type:pt-0" data-position-entity={block.key}>
            {heading === null ? null : <h3 className="mb-2">{heading}</h3>}
            {block.answer === null ? null : (
              <div data-applicability-row={block.key}>
                <ActionRow
                  action={
                    canDecide ? (
                      <Button
                        variant={block.answer.applicability === 'under_assessment' ? 'primary' : 'ghost'}
                        size="small"
                        onClick={() => {
                          setDecided(null);
                          setDeciding(block.key);
                        }}
                      >
                        {block.answer.applicability === 'under_assessment' ? t('obligationApplicability.decide') : t('obligationApplicability.change')}
                      </Button>
                    ) : null
                  }
                >
                  <p className="microlabel text-muted">{t('obligationApplicability.label')}</p>
                  <Meta className="mt-1">
                    <PillRow pills={[presentApplicability(block.answer.applicability, t)]} />
                    {block.answer.decidedBy !== null && block.answer.decidedAt !== null ? (
                      <span>{t('obligationApplicability.decidedBy', { name: block.answer.decidedBy, date: formatDate(block.answer.decidedAt, ctx) })}</span>
                    ) : null}
                  </Meta>
                  <p className="mt-1.5">{block.answer.reason ?? t('obligationApplicability.notDecided')}</p>
                </ActionRow>
              </div>
            )}
            {block.standing === null ? null : (
              <div className={block.answer === null ? undefined : 'mt-3'} data-status-row={block.key}>
                <ActionRow
                  action={
                    canEdit ? (
                      <Button
                        variant="ghost"
                        size="small"
                        onClick={() => {
                          setSaved(false);
                          setEditing(block.standing !== null && 'orgUnitId' in block.standing ? { kind: 'entity', entity: block.standing } : { kind: 'whole' });
                        }}
                      >
                        {t('common.edit')}
                      </Button>
                    ) : null
                  }
                >
                  <p className="microlabel text-muted">{t('obligationStatus.heading')}</p>
                  <Meta className="mt-1">
                    <PillRow pills={[presentCompliance(block.standing.complianceStatus)]} />
                    {owner === null ? null : <span>{t('obligationStatus.ownerLine', { name: String(owner) })}</span>}
                    {review === null ? null : <span>{t('obligationStatus.reviewLine', { date: String(review) })}</span>}
                    {readsGaps ? <OpenGaps obligationId={obligationId} orgUnitId={block.key === 'whole' ? null : block.key} /> : null}
                  </Meta>
                  {block.standing.statusNote === null || block.standing.statusNote === '' ? null : <p className="mt-1.5 whitespace-pre-line">{block.standing.statusNote}</p>}
                  {more.length === 0 ? null : (
                    <Fold title={t('obligationStatus.more')} className="mt-2">
                      <Facts facts={more} />
                    </Fold>
                  )}
                </ActionRow>
              </div>
            )}
          </div>
        );
      })}
      {decided === null ? null : <StatusLine tone="positive">{t('obligationApplicability.saved', { value: presentApplicability(decided, t).label })}</StatusLine>}
      {saved ? <StatusLine tone="positive">{t('common.saved')}</StatusLine> : null}
      {/* Under its own hairline: the part inside would otherwise be the panel's first section and drop it. */}
      {children === undefined || children === null ? null : (
        <div className="mt-4 border-t border-line pt-4" data-position-units="">
          {children}
        </div>
      )}
      {decidingAnswer === null ? null : (
        <DecideOne
          obligationId={obligationId}
          answer={decidingAnswer}
          onClose={(stored) => {
            setDeciding(null);
            if (stored !== null) setDecided(stored);
          }}
        />
      )}
      {editing === null ? null : (
        <EditDialog
          obligationId={obligationId}
          entry={data}
          editing={editing}
          onClose={(stored) => {
            setEditing(null);
            setSaved(stored);
          }}
        />
      )}
    </Panel>
  );
}
