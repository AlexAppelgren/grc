'use client';

import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { Field, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import {
  FOOTPRINT_REQUEST,
  FOUR_EYES_CODE,
  canApprove,
  canWithdraw,
  diffFootprint,
  draftOf,
  historyLine,
  pendingRemovals,
  presentRequestStatus,
  previewLines,
  previewSummary,
  requestTitle,
  toggleTerm,
  type FootprintDraft,
  type PreviewLine,
} from '@/features/footprint/footprint-presentation';
import {
  useApproveFootprintRequest,
  useCreateFootprintRequest,
  useFootprint,
  useFootprintRequests,
  usePreviewFootprintRequest,
  useRejectFootprintRequest,
  useTerms,
  useWithdrawFootprintRequest,
} from '@/features/footprint/hooks';
import type { FootprintChangeRequest, FootprintDimension, FootprintPreview, TaxonomyTerm, TermChange, TermRef } from '@/features/footprint/types';

type ApproveMutation = ReturnType<typeof useApproveFootprintRequest>;
type RejectMutation = ReturnType<typeof useRejectFootprintRequest>;
type CreateMutation = ReturnType<typeof useCreateFootprintRequest>;
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// /admin/footprint (design/screens/admin-footprint.html; FP-01, FP-02, AC-FP1,
// J-6). Toggling a chip never writes: it builds a draft whose counted preview
// comes from a dry run of the request, and Send for approval stores it as
// waiting. A second person with `footprint.approve` approves it behind a
// passkey step-up (the api client opens the ceremony on 403
// step_up_required), or rejects it with a reason. While a request waits, the
// chips are read-only and a struck chip shows what is about to change.

function termLookup(dimensions: readonly FootprintDimension[], terms: readonly TaxonomyTerm[]): Map<string, TermRef> {
  const lookup = new Map<string, TermRef>();
  for (const d of dimensions) for (const term of d.terms) lookup.set(`${d.dimension.key}:${term.key}`, term);
  for (const term of terms) lookup.set(`${term.dimension}:${term.key}`, term);
  return lookup;
}

function withLabels(changes: readonly TermChange[], lookup: Map<string, TermRef>): TaxonomyTerm[] {
  return changes.map((change) => {
    const term = lookup.get(`${change.dimension}:${change.key}`);
    return { dimension: change.dimension, key: change.key, kind: term?.kind ?? null, label: term?.label ?? change.key };
  });
}

/** Every term a dimension can hold, in the taxonomy's order; the held ones when the term list could not be read. */
function chipsOf(dimension: FootprintDimension, terms: readonly TaxonomyTerm[]): TermRef[] {
  const own = terms.filter((term) => term.dimension === dimension.dimension.key && term.active !== false);
  if (own.length === 0) return dimension.terms;
  const known = new Set(own.map((term) => term.key));
  return [...own, ...dimension.terms.filter((term) => !known.has(term.key))];
}

// ——— pending request banner ————————————————————————————————————————

function PendingBanner({
  request,
  userId,
  permissions,
  onApprove,
  onReject,
  onShowPreview,
}: {
  request: FootprintChangeRequest;
  userId: string | null;
  permissions: readonly string[];
  onApprove: () => void;
  onReject: () => void;
  onShowPreview: () => void;
}) {
  const t = useT();
  const ctx = useFormatContext();
  const withdraw = useWithdrawFootprintRequest();
  const date = formatDate(request.requestedAt, ctx);
  const mine = canWithdraw(request, userId);
  const approver = canApprove(request, userId, permissions);
  return (
    <Notice tone="warn" className="grid gap-2" data-pending-request={request.id}>
      <p className="flex flex-wrap items-center gap-2">
        <PillRow pills={[presentRequestStatus(request.status, t)]} />
        <b>{requestTitle(request, t)}</b>
      </p>
      <p>
        {mine
          ? t('footprint.banner.youRequested', { date })
          : `${t('footprint.banner.requestedBy', { name: request.requestedBy.name, date })} ${previewSummary(request.preview, t)}`}
      </p>
      {withdraw.isError ? <ProblemAlert error={withdraw.error} /> : null}
      <ButtonBar className="mt-0 justify-start">
        <Button variant="outline" size="small" onClick={onShowPreview}>
          {t('footprint.banner.seePreview')}
        </Button>
        {mine ? (
          <Button variant="outline" size="small" disabled={withdraw.isPending} onClick={() => withdraw.mutate({ requestId: request.id, version: request.version })}>
            {t('footprint.banner.withdraw')}
          </Button>
        ) : null}
        {approver ? (
          <>
            <Button variant="outline" size="small" onClick={onReject}>
              {t('footprint.banner.reject')}
            </Button>
            <Button size="small" onClick={onApprove}>
              {t('footprint.banner.approve')}
            </Button>
          </>
        ) : null}
      </ButtonBar>
    </Notice>
  );
}

// ——— preview (hides and reveals) ————————————————————————————————————

/** True when a side of the preview moves nothing: every count is known and zero. Decided on the counts, never on the formatted text. */
export function movesNothing(side: FootprintPreview['hidden'] | undefined): boolean {
  return Object.values(side ?? {}).every((entry) => entry.available && entry.count === 0);
}

function PreviewColumns({ preview, pending }: { preview: FootprintPreview | null | undefined; pending: boolean }) {
  const t = useT();
  const { hides, reveals } = previewLines(preview, t);
  const column = (heading: string, lines: PreviewLine[], side: 'hides' | 'reveals') => (
    <div data-preview-side={side}>
      <h3 className="mb-1.5 font-semibold">{heading}</h3>
      {pending ? (
        <StatusLine>{t('common.loading')}</StatusLine>
      ) : movesNothing(side === 'hides' ? preview?.hidden : preview?.revealed) ? (
        <p className="text-muted">{t('footprint.preview.nothing')}</p>
      ) : (
        <ul className="m-0 grid list-none gap-1 p-0">
          {lines.map((line) => (
            <li key={line.key} className={line.available ? 'font-semibold' : 'text-muted'}>
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

function DraftPreview({
  changes,
  title,
  create,
  onDiscard,
  onSent,
}: {
  changes: { adds: TermChange[]; removes: TermChange[] };
  title: string;
  create: CreateMutation;
  onDiscard: () => void;
  onSent: () => void;
}) {
  const t = useT();
  const preview = usePreviewFootprintRequest();
  const signature = JSON.stringify(changes);
  const { mutate } = preview;

  // A dry run per change of the draft: the counted preview, nothing stored.
  useEffect(() => {
    mutate(JSON.parse(signature) as { adds: TermChange[]; removes: TermChange[] });
  }, [signature, mutate]);

  return (
    <Panel title={t('footprint.preview.title', { title })} data-draft-preview="">
      <PreviewColumns preview={preview.data} pending={preview.isPending} />
      {preview.isError ? <ProblemAlert error={preview.error} /> : null}
      {create.isError ? <ProblemAlert error={create.error} /> : null}
      <div className="mt-3.5 flex flex-wrap items-center justify-end gap-3">
        <span className="text-meta text-muted">{t('footprint.preview.secondPerson')}</span>
        <ButtonBar className="mt-0">
          <Button variant="outline" onClick={onDiscard} disabled={create.isPending}>
            {t('footprint.preview.discard')}
          </Button>
          <Button disabled={create.isPending} onClick={() => create.mutate(changes, { onSuccess: onSent })}>
            {t('footprint.preview.send')}
          </Button>
        </ButtonBar>
      </div>
    </Panel>
  );
}

// ——— approve and reject ————————————————————————————————————————————

function ApproveDialog({ request, approve, onClose, onDone }: { request: FootprintChangeRequest; approve: ApproveMutation; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const fourEyes = hasProblemCode(approve.error, FOUR_EYES_CODE);
  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next && !approve.isPending) onClose();
      }}
      title={t('footprint.approve.title', { title: requestTitle(request, t) })}
      description={`${previewSummary(request.preview, t)} ${t('footprint.approve.body')}`}
    >
      {fourEyes ? (
        <Notice tone="bad" data-four-eyes="">
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
        <Field id="reject-reason" label={t('footprint.reject.reason')} hint={t('footprint.reject.reasonHint')} error={blank ? t('footprint.reject.reasonRequired') : undefined}>
          <TextArea id="reject-reason" placeholder={t('footprint.reject.reasonPlaceholder')} value={note} autoFocus onChange={(e) => setNote(e.target.value)} />
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

function History({ requests }: { requests: readonly FootprintChangeRequest[] }) {
  const t = useT();
  const ctx = useFormatContext();
  const decided = requests.filter((request) => request.status !== 'pending');
  return (
    <Panel title={t('footprint.history.title')} data-footprint-history="">
      {decided.length === 0 ? (
        <p className="text-muted">{t('footprint.history.empty')}</p>
      ) : (
        <ul className="m-0 grid list-none gap-2.5 p-0">
          {decided.map((request) => {
            const line = historyLine(request, t, ctx);
            return (
              <li key={request.id} data-history-entry={request.status}>
                <time className="mr-2 text-meta text-muted">{line.when}</time>
                <b className="mr-1">{line.who}</b>
                {line.text}
              </li>
            );
          })}
        </ul>
      )}
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
  // Held here, not in the panel or the dialog that triggers them: each success
  // unmounts its trigger (the request makes the chips read-only; a decision
  // clears the pending request), and the confirmation must still be shown.
  const create = useCreateFootprintRequest();
  const approve = useApproveFootprintRequest();
  const reject = useRejectFootprintRequest();
  const session = useSession();
  const permissions = usePermissions() ?? [];
  const userId = session.me?.user.id ?? null;

  const [draft, setDraft] = useState<FootprintDraft | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [showPendingPreview, setShowPendingPreview] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const dimensions = useMemo(() => footprint.data?.dimensions ?? [], [footprint.data]);
  const pending = footprint.data?.pendingRequest ?? null;
  const canRequest = permissions.includes(FOOTPRINT_REQUEST);
  const editable = canRequest && pending === null;
  const current = draft ?? draftOf(dimensions);
  const lookup = useMemo(() => termLookup(dimensions, terms.data ?? []), [dimensions, terms.data]);
  const changes = diffFootprint(dimensions, current);
  const changed = changes.adds.length + changes.removes.length > 0;

  if (footprint.isPending) {
    return (
      <>
        <BackLink href="/admin" label={t('admin.back')} />
        <PageHead title={t('footprint.title')} lede={t('footprint.lede')} />
        <LoadingState rows={1} />
      </>
    );
  }
  if (footprint.isError) {
    return (
      <>
        <BackLink href="/admin" label={t('admin.back')} />
        <PageHead title={t('footprint.title')} lede={t('footprint.lede')} />
        <ErrorState title={t('footprint.errorTitle')} onRetry={() => void footprint.refetch()} />
      </>
    );
  }

  const draftTitle = requestTitle({ adds: withLabels(changes.adds, lookup), removes: withLabels(changes.removes, lookup) }, t);

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('footprint.title')} lede={t('footprint.lede')} />

      {status !== null ? <StatusLine tone="positive">{status}</StatusLine> : null}

      {pending !== null ? (
        <PendingBanner
          request={pending}
          userId={userId}
          permissions={permissions}
          onApprove={() => {
            approve.reset();
            setDialog('approve');
          }}
          onReject={() => {
            reject.reset();
            setDialog('reject');
          }}
          onShowPreview={() => setShowPendingPreview((shown) => !shown)}
        />
      ) : null}

      {pending !== null && showPendingPreview ? (
        <Panel title={t('footprint.preview.title', { title: requestTitle(pending, t) })} data-pending-preview="">
          <PreviewColumns preview={pending.preview} pending={false} />
        </Panel>
      ) : null}

      {!canRequest ? <Notice>{t('footprint.readOnly')}</Notice> : pending !== null ? <Notice>{t('footprint.pendingReadOnly')}</Notice> : null}

      <Panel title={t('footprint.dimensions')} data-footprint-dimensions="">
        {dimensions.map((dimension) => {
          const key = dimension.dimension.key;
          const held = current[key] ?? new Set<string>();
          const struck = pendingRemovals(pending, key);
          return (
            <section key={key} className="mb-4 last:mb-0" data-dimension={key}>
              <h3 className="mb-2 font-semibold">{dimension.dimension.label}</h3>
              <ChipRow>
                {chipsOf(dimension, terms.data ?? []).map((term) => (
                  <Chip
                    key={term.key}
                    pressed={held.has(term.key)}
                    struck={struck.has(term.key)}
                    disabled={!editable}
                    onClick={() => {
                      setStatus(null);
                      setDraft(toggleTerm(current, key, term.key));
                    }}
                  >
                    {term.label}
                  </Chip>
                ))}
                {held.size === 0 ? <span className="text-meta text-muted">{t('footprint.notRestricted')}</span> : null}
              </ChipRow>
            </section>
          );
        })}
        <p className="mt-3 text-meta text-muted">{t('footprint.dimensionNote')}</p>
      </Panel>

      {editable && changed ? (
        <DraftPreview
          changes={changes}
          title={draftTitle}
          create={create}
          onDiscard={() => setDraft(null)}
          onSent={() => {
            setDraft(null);
            setStatus(t('footprint.sent'));
          }}
        />
      ) : null}

      {requests.isError ? <ProblemAlert error={requests.error} /> : <History requests={requests.data?.items ?? []} />}

      {pending !== null && dialog === 'approve' ? (
        <ApproveDialog
          request={pending}
          approve={approve}
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            setStatus(t('footprint.approvedDone'));
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
            setStatus(t('footprint.rejectedDone'));
          }}
        />
      ) : null}
    </>
  );
}
