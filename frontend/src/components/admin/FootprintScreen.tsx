'use client';

import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { CheckGroup, CheckRow, Field, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import {
  FOOTPRINT_REQUEST,
  FOUR_EYES_CODE,
  REQUEST_PENDING_CODE,
  canApprove,
  canWithdraw,
  diffFootprint,
  draftAfter,
  draftOf,
  hidesSomething,
  historyLine,
  marketLevelLabel,
  narrowedGroups,
  pendingAdditions,
  pendingRemovals,
  pendingTermPill,
  presentRequestStatus,
  previewLines,
  previewSummary,
  reachLines,
  requestTitle,
  scopeGroups,
  toggleTerm,
  type FootprintDraft,
  type PreviewLine,
  type ScopeGroup,
} from '@/features/footprint/footprint-presentation';
import {
  useApproveFootprintRequest,
  useCreateFootprintRequest,
  useFootprint,
  useFootprintRequests,
  useJurisdictions,
  usePreviewFootprintRequest,
  useRejectFootprintRequest,
  useTerms,
  useUnwatchMarket,
  useWatchMarket,
  useWithdrawFootprintRequest,
} from '@/features/footprint/hooks';
import type { FootprintChangeRequest, FootprintDimension, FootprintPreview, Market, TaxonomyTerm, TermChange } from '@/features/footprint/types';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { humanisePermission, usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// /admin/footprint, shown as Regulatory scope (design/screens/admin-footprint.html,
// states 1 to 16; FP-01, FP-02, AC-FP1, J-6). The page opens read-only: every term a
// checkbox-shaped glyph, nothing in the tab order. "Propose a change" turns the groups
// into checkboxes and opens the change panel, whose preview is a dry run of the request;
// nothing is stored until "Request approval". A second person with footprint.approve
// approves behind a passkey step-up (the api client opens the ceremony on 403
// step_up_required) or rejects with a reason; the requester can withdraw. After a send,
// a decision or a withdrawal the message goes to the one status line and focus follows it.
// The markets panel (states 17 to 19; FP-04, D-27, D-30) lists every country with its
// computed level: an operating market changes only through a request above, and a
// Watching toggle saves at once, with no second person, because watching hides nothing.

type ApproveMutation = ReturnType<typeof useApproveFootprintRequest>;
type RejectMutation = ReturnType<typeof useRejectFootprintRequest>;
type CreateMutation = ReturnType<typeof useCreateFootprintRequest>;
type WithdrawMutation = ReturnType<typeof useWithdrawFootprintRequest>;

/** Where the focus goes after the next render: a fresh object each time, so the same target can be asked for twice. */
type FocusRequest = { target: 'status' | 'propose' | 'first-checkbox' | 'banner' };

const FOCUS_SELECTOR: Record<Exclude<FocusRequest['target'], 'status'>, string> = {
  propose: '[data-propose]',
  'first-checkbox': '[data-footprint-dimensions] input[type="checkbox"]',
  banner: '[data-pending-request]',
};

/** A draft and the stored scope it was taken from: the diff means what the person chose only against that scope. */
type Draft = { base: string; held: FootprintDraft };

function scopeSignature(dimensions: readonly FootprintDimension[]): string {
  return JSON.stringify(dimensions.map((d) => [d.dimension.key, d.terms.map((term) => term.key)]));
}

const REJECT_REASON = 'reject-reason';

/** The changes with their labels, read from the groups they were ticked in (a held term no longer active is only there). */
function withLabels(changes: readonly TermChange[], groups: readonly ScopeGroup[]): TaxonomyTerm[] {
  return changes.map((change) => {
    const row = groups.find((group) => group.dimension.key === change.dimension)?.rows.find((r) => r.term.key === change.key);
    return { ...change, kind: null, label: row?.term.label ?? change.key };
  });
}

/** True when a side of the preview moves nothing: every count is known and zero. Decided on the counts, never on the formatted text. */
export function movesNothing(side: FootprintPreview['hidden'] | undefined): boolean {
  return Object.values(side ?? {}).every((entry) => entry.available && entry.count === 0);
}

// ——— groups ————————————————————————————————————————————————————————

/** A 16px checkbox-shaped glyph: ticked when held. Not a control, so nothing greys out and nothing takes focus. */
function TermGlyph({ held }: { held: boolean }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="mt-0.5 size-4 flex-none">
      <rect x="1.5" y="1.5" width="13" height="13" rx="3" className="fill-none stroke-line-strong" />
      {held ? <path d="M4.5 8.2l2.4 2.4 4.6-5" className="fill-none stroke-fg" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" /> : null}
    </svg>
  );
}

function ReadGroup({ group, pending }: { group: ScopeGroup; pending: FootprintChangeRequest | null }) {
  const t = useT();
  const key = group.dimension.key;
  const adds = pendingAdditions(pending, key);
  const removes = pendingRemovals(pending, key);
  // A group with nothing held does not restrict, and an opt-in one follows nothing; it lists its terms only when a waiting request adds one.
  const listed = group.rows.some((row) => row.held || adds.has(row.term.key));
  return (
    <div data-dimension={key}>
      <h3 className="mb-1 font-medium">{group.dimension.label}</h3>
      {group.mirrored ? <p className="mb-1 text-meta text-muted">{t('footprint.jurisdictionHint')}</p> : null}
      {listed ? (
        <ul className="m-0 list-none p-0">
          {group.rows.map(({ term, held }) => {
            const mark = adds.has(term.key) ? 'add' : removes.has(term.key) ? 'remove' : null;
            return (
              <li key={term.key} data-term={term.key} className="flex min-w-0 items-start gap-2 py-1">
                <TermGlyph held={held} />
                <span className="min-w-0">
                  {term.label}{' '}
                  <span className="sr-only">{held ? t('footprint.term.in') : t('footprint.term.out')}</span>
                  {mark !== null ? (
                    <>
                      {' '}
                      <span className="inline-flex align-top">
                        <PillRow pills={[pendingTermPill(mark, t)]} />
                      </span>
                    </>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p>{group.optIn ? t('footprint.noneFollowed') : t('footprint.notRestricted')}</p>
      )}
    </div>
  );
}

function EditGroup({ group, draft, disabled, onToggle }: { group: ScopeGroup; draft: FootprintDraft; disabled: boolean; onToggle: (key: string) => void }) {
  const t = useT();
  const key = group.dimension.key;
  const held = draft[key] ?? new Set<string>();
  const hint = held.size === 0 ? (group.optIn ? t('footprint.noneFollowed') : t('footprint.notRestricted')) : group.mirrored ? t('footprint.jurisdictionHint') : undefined;
  return (
    <div data-dimension={key}>
      <CheckGroup legend={group.dimension.label} hint={hint}>
        {group.rows.map(({ term }) => (
          <CheckRow key={term.key} id={`scope-${key}-${term.key}`} label={term.label} checked={held.has(term.key)} disabled={disabled} onChange={() => onToggle(term.key)} />
        ))}
      </CheckGroup>
    </div>
  );
}

// ——— preview (hides and reveals) ————————————————————————————————————

function PreviewColumns({ preview, pending }: { preview: FootprintPreview | null | undefined; pending: boolean }) {
  const t = useT();
  const { hides, reveals } = previewLines(preview, t);
  const column = (heading: string, lines: PreviewLine[], side: 'hides' | 'reveals') => (
    <div data-preview-side={side}>
      <h3 className="mb-1.5 font-medium">{heading}</h3>
      {pending ? (
        <StatusLine>{t('common.loading')}</StatusLine>
      ) : movesNothing(side === 'hides' ? preview?.hidden : preview?.revealed) ? (
        <p className="text-muted">{t('footprint.preview.nothing')}</p>
      ) : (
        <ul className="m-0 grid list-none gap-1 p-0">
          {lines.map((line) => (
            <li key={line.key} className={line.available ? 'font-semibold' : 'text-meta text-muted'}>
              {line.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {column(t('footprint.preview.hidesHeading'), hides, 'hides')}
      {column(t('footprint.preview.revealsHeading'), reveals, 'reveals')}
    </div>
  );
}

/** What a change does to every member, said once: in the change panel and in the approve dialog. */
function ConsequenceNotice({ narrowed }: { narrowed: readonly FootprintDimension[] }) {
  const t = useT();
  return (
    <Notice tone="warn" className="mt-4 mb-0 grid gap-2">
      <p>{t('footprint.preview.hidesForAll')}</p>
      {narrowed.map((d) => (
        <p key={d.dimension.key}>{t('footprint.preview.narrows', { group: d.dimension.label })}</p>
      ))}
    </Notice>
  );
}

/** The counted preview of a draft that differs: a dry run per change of the draft, nothing stored. */
function DraftPreview({ changes, narrowed }: { changes: { adds: TermChange[]; removes: TermChange[] }; narrowed: readonly FootprintDimension[] }) {
  const preview = usePreviewFootprintRequest();
  const signature = JSON.stringify(changes);
  const { mutate } = preview;

  useEffect(() => {
    mutate(JSON.parse(signature) as { adds: TermChange[]; removes: TermChange[] });
  }, [signature, mutate]);

  return (
    <>
      <PreviewColumns preview={preview.data} pending={preview.isPending} />
      {preview.isError ? <ProblemAlert error={preview.error} /> : null}
      {narrowed.length > 0 || hidesSomething(preview.data) ? <ConsequenceNotice narrowed={narrowed} /> : null}
    </>
  );
}

function ChangePanel({
  dimensions,
  groups,
  draft,
  create,
  onCancel,
  onSent,
  onRequestPending,
}: {
  dimensions: readonly FootprintDimension[];
  groups: readonly ScopeGroup[];
  draft: FootprintDraft;
  create: CreateMutation;
  onCancel: () => void;
  onSent: () => void;
  onRequestPending: () => void;
}) {
  const t = useT();
  const changes = diffFootprint(dimensions, draft);
  const changed = changes.adds.length + changes.removes.length > 0;
  const title = changed ? t('footprint.preview.title', { title: requestTitle({ adds: withLabels(changes.adds, groups), removes: withLabels(changes.removes, groups) }, t) }) : t('footprint.preview.untitled');
  return (
    <Panel title={title} data-draft-preview="">
      {changed ? <DraftPreview changes={changes} narrowed={narrowedGroups(dimensions, draft)} /> : <p>{t('footprint.draft.nothing')}</p>}
      {create.isError ? <ProblemAlert error={create.error} codes={{ [REQUEST_PENDING_CODE]: t('footprint.requestPending') }} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={onCancel} disabled={create.isPending}>
          {t('common.cancel')}
        </Button>
        {changed ? (
          <Button
            disabled={create.isPending}
            onClick={() =>
              create.mutate(changes, {
                onSuccess: onSent,
                onError: (error) => {
                  if (hasProblemCode(error, REQUEST_PENDING_CODE)) onRequestPending();
                },
              })
            }
          >
            {t('footprint.preview.send')}
          </Button>
        ) : null}
      </ButtonBar>
    </Panel>
  );
}

// ——— the waiting request ————————————————————————————————————————————

function PendingBanner({
  request,
  userId,
  permissions,
  previewId,
  previewShown,
  withdraw,
  onTogglePreview,
  onApprove,
  onReject,
  onWithdrawn,
}: {
  request: FootprintChangeRequest;
  userId: string | null;
  permissions: readonly string[];
  previewId: string;
  previewShown: boolean;
  withdraw: WithdrawMutation;
  onTogglePreview: () => void;
  onApprove: () => void;
  onReject: () => void;
  onWithdrawn: () => void;
}) {
  const t = useT();
  const ctx = useFormatContext();
  const date = formatDate(request.requestedAt, ctx);
  const mine = canWithdraw(request, userId);
  const approver = canApprove(request, userId, permissions);
  // Every text inside the warn notice is the text colour (foundations.md, "Restricted setting").
  return (
    <>
      {/* Focusable, not tabbable: the focus lands here when a request that started waiting ends an edit. */}
      <Notice tone="warn" className="grid gap-2" tabIndex={-1} data-pending-request={request.id}>
        <p className="flex flex-wrap items-center gap-2">
          <PillRow pills={[presentRequestStatus(request.status, t)]} />
          <b>{requestTitle(request, t)}</b>
        </p>
        <p>{mine ? t('footprint.banner.youRequested', { date }) : `${t('footprint.banner.requestedBy', { name: request.requestedBy.name, date })} ${previewSummary(request.preview, t)}`}</p>
        {permissions.includes(FOOTPRINT_REQUEST) ? <p>{t('footprint.banner.blocks')}</p> : null}
        <Button variant="ghost" size="small" className="justify-self-start" aria-expanded={previewShown} aria-controls={previewId} onClick={onTogglePreview}>
          {t('footprint.banner.seePreview')}
        </Button>
        {mine ? (
          <ButtonBar className="mt-2">
            <Button variant="outline" disabled={withdraw.isPending} onClick={() => withdraw.mutate({ requestId: request.id, version: request.version }, { onSuccess: onWithdrawn })}>
              {t('footprint.banner.withdraw')}
            </Button>
          </ButtonBar>
        ) : approver ? (
          <ButtonBar className="mt-2">
            <Button variant="outline" onClick={onReject}>
              {t('footprint.banner.reject')}
            </Button>
            <Button onClick={onApprove}>{t('footprint.banner.approve')}</Button>
          </ButtonBar>
        ) : null}
      </Notice>
      {withdraw.isError ? <ProblemAlert error={withdraw.error} className="-mt-2 mb-4 text-meta text-negative" /> : null}
    </>
  );
}

// ——— approve and reject ————————————————————————————————————————————

function ApproveDialog({
  request,
  dimensions,
  approve,
  onClose,
  onDone,
}: {
  request: FootprintChangeRequest;
  dimensions: readonly FootprintDimension[];
  approve: ApproveMutation;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useT();
  const fourEyes = hasProblemCode(approve.error, FOUR_EYES_CODE);
  const narrowed = narrowedGroups(dimensions, draftAfter(dimensions, request));
  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next && !approve.isPending) onClose();
      }}
      title={t('footprint.approve.title', { title: requestTitle(request, t) })}
      description={previewSummary(request.preview, t)}
    >
      {narrowed.length > 0 || hidesSomething(request.preview) ? <ConsequenceNotice narrowed={narrowed} /> : null}
      {fourEyes ? (
        <Notice tone="bad" className="mt-4 mb-0" data-four-eyes="">
          {t('footprint.fourEyes')}
        </Notice>
      ) : approve.isError ? (
        <ProblemAlert error={approve.error} codes={{ step_up_required: t('problem.stepUpCancelled') }} />
      ) : null}
      <ButtonBar>
        <Button variant="outline" onClick={onClose} disabled={approve.isPending}>
          {t('common.cancel')}
        </Button>
        <Button disabled={approve.isPending || fourEyes} onClick={() => approve.mutate({ requestId: request.id, version: request.version }, { onSuccess: onDone })}>
          {t('footprint.approve.button')}
        </Button>
      </ButtonBar>
    </Modal>
  );
}

function RejectDialog({ request, reject, onClose, onDone }: { request: FootprintChangeRequest; reject: RejectMutation; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const [note, setNote] = useState('');
  const [blank, setBlank] = useState(false);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (note.trim() === '') {
      setBlank(true);
      document.getElementById(REJECT_REASON)?.focus();
      return;
    }
    setBlank(false);
    reject.mutate({ requestId: request.id, body: { note: note.trim() }, version: request.version }, { onSuccess: onDone });
  };
  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next && !reject.isPending) onClose();
      }}
      title={t('footprint.reject.title')}
    >
      <form onSubmit={submit} noValidate aria-busy={reject.isPending}>
        <Field id={REJECT_REASON} label={t('footprint.reject.reason')} hint={t('footprint.reject.reasonHint')} error={blank ? t('footprint.reject.reasonRequired') : undefined}>
          <TextArea
            id={REJECT_REASON}
            placeholder={t('footprint.reject.reasonPlaceholder')}
            value={note}
            aria-describedby={blank ? `${REJECT_REASON}-hint ${REJECT_REASON}-error` : `${REJECT_REASON}-hint`}
            aria-invalid={blank}
            aria-required
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
        {reject.isError ? <ProblemAlert error={reject.error} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={reject.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="danger" disabled={reject.isPending}>
            {t('footprint.reject.button')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

// ——— history ——————————————————————————————————————————————————————

function History({ requests, more, loadingMore, onMore }: { requests: readonly FootprintChangeRequest[]; more: boolean; loadingMore: boolean; onMore: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const decided = requests.filter((request) => request.status !== 'pending');
  return (
    <Panel title={t('footprint.history.title')} data-footprint-history="">
      {decided.length === 0 ? (
        <p className="text-muted">{t('footprint.history.empty')}</p>
      ) : (
        <ul className="m-0 list-none p-0">
          {decided.map((request) => {
            const line = historyLine(request, t, ctx);
            return (
              <li key={request.id} data-history-entry={request.status} className="border-b border-line py-2.5 last:border-b-0">
                <time className="block text-meta text-muted">{line.when}</time>
                <b>{line.who}</b>
                {' '}
                {line.text}
              </li>
            );
          })}
        </ul>
      )}
      {more ? (
        <Button variant="outline" size="small" className="mt-3" disabled={loadingMore} onClick={onMore}>
          {t('footprint.history.showMore')}
        </Button>
      ) : null}
    </Panel>
  );
}

// ——— markets we watch ——————————————————————————————————————————————

/** One country: "Operating" as meta text, a Watching toggle for someone who can watch, or the level in words. */
function MarketRowItem({ market, canWatch, onToggle }: { market: Market; canWatch: boolean; onToggle: () => void }) {
  const t = useT();
  return (
    <li data-market={market.jurisdiction.key} className="flex min-h-11 items-center justify-between gap-3 border-b border-line py-1.5 last:border-b-0">
      <span className="min-w-0">{market.jurisdiction.label}</span>
      {market.level === 'operating' || !canWatch ? (
        <span className="text-meta text-muted">{marketLevelLabel(market.level, t)}</span>
      ) : (
        <Chip pressed={market.level === 'watching'} onClick={onToggle}>
          {t('footprint.markets.watching')}{' '}
          <span className="sr-only">{market.jurisdiction.label}</span>
        </Chip>
      )}
    </li>
  );
}

function MarketsPanel({ markets, canWatch }: { markets: readonly Market[]; canWatch: boolean }) {
  const t = useT();
  const jurisdictions = useJurisdictions();
  const watch = useWatchMarket();
  const unwatch = useUnwatchMarket();
  // The market whose save failed: the toggle keeps the level the server holds and the reason renders under the list.
  const [notSaved, setNotSaved] = useState<string | null>(null);
  const busy = watch.isPending || unwatch.isPending;
  const toggle = (market: Market) => {
    if (busy) return;
    setNotSaved(null);
    const save = market.level === 'watching' ? unwatch : watch;
    save.mutate(market.jurisdiction.key, { onError: () => setNotSaved(market.jurisdiction.label) });
  };
  const reach = reachLines(markets, jurisdictions.data ?? [], t);
  return (
    <Panel title={t('footprint.markets.title')} data-markets="">
      {canWatch ? null : <Notice className="mb-3">{t('footprint.markets.approverOnly', { permission: humanisePermission(FOOTPRINT_REQUEST) })}</Notice>}
      <p className="mb-3 text-meta text-muted">{t('footprint.markets.intro')}</p>
      <ul className="m-0 list-none p-0" aria-busy={busy}>
        {markets.map((market) => (
          <MarketRowItem key={market.jurisdiction.key} market={market} canWatch={canWatch} onToggle={() => toggle(market)} />
        ))}
      </ul>
      {notSaved !== null ? (
        <Notice tone="bad" className="mt-3 mb-0" data-market-not-saved="">
          {t('footprint.markets.notSaved', { market: notSaved })}
        </Notice>
      ) : null}
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {reach.length > 0 ? (
          <div data-markets-reach="">
            <h3 className="mb-1 font-medium">{t('footprint.markets.alsoIncluded')}</h3>
            {reach.map((line) => (
              <p key={line} className="text-meta text-muted">
                {line}
              </p>
            ))}
          </div>
        ) : null}
        <div>
          <h3 className="mb-1 font-medium">{t('footprint.markets.everywhereElse')}</h3>
          <p className="text-meta text-muted">{t('footprint.markets.sweep')}</p>
        </div>
      </div>
    </Panel>
  );
}

// ——— the screen ———————————————————————————————————————————————————

type Dialog = 'approve' | 'reject' | null;

export function FootprintScreen() {
  const t = useT();
  const footprint = useFootprint();
  const terms = useTerms();
  const requests = useFootprintRequests();
  // Held here, not in the panel, banner or dialog that triggers them: each success
  // unmounts its trigger, and the confirmation must still reach the status line.
  const create = useCreateFootprintRequest();
  const approve = useApproveFootprintRequest();
  const reject = useRejectFootprintRequest();
  const withdraw = useWithdrawFootprintRequest();
  const session = useSession();
  const permissions = usePermissions() ?? [];
  const userId = session.me?.user.id ?? null;

  const [draft, setDraft] = useState<Draft | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [previewShown, setPreviewShown] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [focus, setFocus] = useState<FocusRequest | null>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);

  // After the render that follows a send, a decision, a withdrawal or a cancel. On a
  // timer, so it runs after a closing dialog hands focus back to a trigger that is gone.
  useEffect(() => {
    if (focus === null) return;
    const timer = window.setTimeout(() => {
      const target = focus.target === 'status' ? statusRef.current : document.querySelector<HTMLElement>(FOCUS_SELECTOR[focus.target]);
      target?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [focus]);

  const dimensions = useMemo(() => footprint.data?.dimensions ?? [], [footprint.data]);
  const groups = useMemo(() => scopeGroups(dimensions, terms.data ?? []), [dimensions, terms.data]);
  const base = useMemo(() => scopeSignature(dimensions), [dimensions]);
  const pending = footprint.data?.pendingRequest ?? null;
  const canRequest = permissions.includes(FOOTPRINT_REQUEST);
  // A request that starts waiting, or a scope that changed under the draft, ends the edit
  // for good: kept, the old snapshot would come back later proposing to undo someone
  // else's approved change. Cleared during render, so no frame shows the stale draft.
  const stale = draft !== null && (!canRequest || pending !== null || draft.base !== base);
  if (stale) {
    setDraft(null);
    setFocus({ target: pending !== null ? 'banner' : 'propose' });
  }
  // The draft being edited; null in the read state.
  const editing = draft !== null && !stale ? draft.held : null;

  const announce = (message: string) => {
    create.reset();
    setStatus(message);
    setFocus({ target: 'status' });
  };

  const head = (actions?: ReactNode) => (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('footprint.title')} lede={t('footprint.lede')} actions={actions} />
    </>
  );

  if (footprint.isPending || terms.isPending) {
    return (
      <>
        {head()}
        <LoadingState />
      </>
    );
  }
  if (footprint.isError || terms.isError) {
    return (
      <>
        {head()}
        <ErrorState
          title={t('footprint.errorTitle')}
          onRetry={() => {
            if (footprint.isError) void footprint.refetch();
            if (terms.isError) void terms.refetch();
          }}
        />
      </>
    );
  }

  const previewId = 'footprint-request-preview';

  return (
    <>
      {head(
        canRequest && pending === null && editing === null ? (
          <Button
            variant="danger"
            data-propose=""
            onClick={() => {
              create.reset();
              setStatus(null);
              setDraft({ base, held: draftOf(dimensions) });
              setFocus({ target: 'first-checkbox' });
            }}
          >
            {t('footprint.propose')}
          </Button>
        ) : undefined,
      )}

      <p ref={statusRef} role="status" tabIndex={-1} className="mb-3 font-medium empty:hidden" data-status-line="">
        {status}
      </p>

      {pending === null ? (
        <Notice>{t('footprint.rule')}</Notice>
      ) : (
        <PendingBanner
          request={pending}
          userId={userId}
          permissions={permissions}
          previewId={previewId}
          previewShown={previewShown}
          withdraw={withdraw}
          onTogglePreview={() => setPreviewShown((shown) => !shown)}
          onApprove={() => {
            approve.reset();
            setDialog('approve');
          }}
          onReject={() => {
            reject.reset();
            setDialog('reject');
          }}
          onWithdrawn={() => announce(t('footprint.withdrawnDone'))}
        />
      )}
      {/* Someone else's request got in first: said under the banner that now shows it. */}
      {pending !== null && hasProblemCode(create.error, REQUEST_PENDING_CODE) ? (
        <ProblemAlert error={create.error} codes={{ [REQUEST_PENDING_CODE]: t('footprint.requestPending') }} className="-mt-2 mb-4 text-meta text-negative" />
      ) : null}

      {pending !== null ? (
        <Panel id={previewId} hidden={!previewShown} data-pending-preview="">
          <PreviewColumns preview={pending.preview} pending={false} />
        </Panel>
      ) : null}

      <Panel data-footprint-dimensions="">
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2 xl:grid-cols-3">
          {groups.map((group) =>
            editing !== null ? (
              <EditGroup
                key={group.dimension.key}
                group={group}
                draft={editing}
                disabled={create.isPending}
                onToggle={(key) => setDraft((current) => current && { ...current, held: toggleTerm(current.held, group.dimension.key, key) })}
              />
            ) : (
              <ReadGroup key={group.dimension.key} group={group} pending={pending} />
            ),
          )}
        </div>
      </Panel>

      {editing !== null ? (
        <ChangePanel
          dimensions={dimensions}
          groups={groups}
          draft={editing}
          create={create}
          onCancel={() => {
            create.reset();
            setDraft(null);
            setFocus({ target: 'propose' });
          }}
          onSent={() => {
            setDraft(null);
            announce(t('footprint.sent'));
          }}
          onRequestPending={() => void footprint.refetch()}
        />
      ) : null}

      {requests.isError ? (
        <ProblemAlert error={requests.error} />
      ) : (
        <History
          requests={requests.data?.pages.flatMap((page) => page.items) ?? []}
          more={requests.hasNextPage}
          loadingMore={requests.isFetchingNextPage}
          onMore={() => void requests.fetchNextPage()}
        />
      )}

      <MarketsPanel markets={footprint.data.markets} canWatch={canRequest} />

      {pending !== null && dialog === 'approve' ? (
        <ApproveDialog
          request={pending}
          dimensions={dimensions}
          approve={approve}
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            announce(t('footprint.approvedDone'));
          }}
        />
      ) : null}
      {pending !== null && dialog === 'reject' ? (
        <RejectDialog
          request={pending}
          reject={reject}
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            announce(t('footprint.rejectedDone'));
          }}
        />
      ) : null}
    </>
  );
}
