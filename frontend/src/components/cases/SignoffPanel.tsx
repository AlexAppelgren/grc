'use client';

import { isAxiosError } from 'axios';
import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Panel } from '@/components/ui/Panel';
import { ProblemAlert } from '@/components/ui/States';
import { closeKindOf } from '@/features/cases/case-presentation';
import { staleWriteOf, useApproveSignoff, useReloadCase, useRequestSignoff, useSendBackSignoff } from '@/features/cases/hooks';
import type { CasePanelProps, CaseWorkflow } from '@/features/cases/types';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { STEP_UP_REQUIRED_CODE } from '@/shared/utils/api-client';
import { formatDate, formatDateTime } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// The sign-off panel on the change page (CAS-06; design/screens/tenant-change.html,
// "Sign-off" and "Closed, signed off"). Implementing: Request sign-off, enabled
// only when the server's `canRequestSignoff` says so, with the reason read off
// `openActionCount`. Waiting: Sign off and close with a passkey (the api client
// opens the shared prompt on 403 `step_up_required` and sends it once more), or
// Send back with a note. Signed off: both names, final.
//
// The panel holds no assertion of its own: who may sign off is the server's
// answer, and every refusal is its code said in words where it happened.

const WORK = 'cases.work';
const SIGNOFF = 'cases.signoff';

/** The count a 409 `open_actions` carries beside its code, or null when it carries none. */
function refusedOpenActions(error: unknown): number | null {
  if (!hasProblemCode(error, 'open_actions') || !isAxiosError(error)) return null;
  const count = (error.response?.data as { openActionCount?: unknown }).openActionCount;
  return typeof count === 'number' ? count : null;
}

function WriteRefusal({ error, changeId, codes }: { error: unknown; changeId: string; codes: Record<string, string> }) {
  const t = useT();
  const reload = useReloadCase(changeId);
  if (staleWriteOf(error) !== null) {
    return (
      <div role="alert" className="mt-2.5 text-meta text-negative">
        <p>{t('cases.staleWrite.body')}</p>
        <Button variant="outline" size="small" className="mt-2" onClick={() => void reload()}>
          {t('cases.staleWrite.reload')}
        </Button>
      </div>
    );
  }
  return <ProblemAlert error={error} codes={codes} />;
}

function RequestSignoff({ changeId, workflow, canWork }: { changeId: string; workflow: CaseWorkflow; canWork: boolean }) {
  const t = useT();
  const request = useRequestSignoff(changeId, workflow.version);
  const reason = workflow.canRequestSignoff
    ? null
    : workflow.openActionCount > 0
      ? t('caseSignoff.notReady.openActions', {
          count: workflow.openActionCount,
        })
      : t('caseSignoff.notReady.evidence');
  const reasonId = `signoff-reason-${workflow.id}`;
  const counted = refusedOpenActions(request.error);
  const codes = {
    open_actions: t('caseSignoff.refused.openActions', {
      count: counted ?? workflow.openActionCount,
    }),
    evidence_missing: t('caseSignoff.refused.evidenceMissing'),
  };

  return (
    <>
      <p id={reasonId} className={reason === null ? 'text-body' : 'text-meta text-muted'} data-signoff-reason="">
        {reason ?? t('caseSignoff.ready')}
      </p>
      {canWork ? (
        <ButtonBar>
          <Button disabled={!workflow.canRequestSignoff || request.isPending} aria-describedby={reasonId} onClick={() => request.mutate()}>
            {t('caseSignoff.request')}
          </Button>
        </ButtonBar>
      ) : null}
      {request.isError ? <WriteRefusal error={request.error} changeId={changeId} codes={codes} /> : null}
    </>
  );
}

function SendBackModal({ changeId, workflow, requester, onOpenChange }: { changeId: string; workflow: CaseWorkflow; requester: string; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const [note, setNote] = useState('');
  const [tried, setTried] = useState(false);
  const sendBack = useSendBackSignoff(changeId, workflow.version);
  const missing = note.trim() === '';

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (missing) return;
    sendBack.mutate({ note: note.trim() }, { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Modal open onOpenChange={onOpenChange} title={t('caseSignoff.sendBackTitle')} description={t('caseSignoff.sendBackBody', { name: requester })}>
      <form onSubmit={submit} noValidate aria-busy={sendBack.isPending}>
        <Field id="signoff-send-back-note" label={t('caseSignoff.sendBackNote')} error={tried && missing ? t('caseSignoff.sendBackNoteRequired') : undefined}>
          <TextArea id="signoff-send-back-note" value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
        {sendBack.isError ? <WriteRefusal error={sendBack.error} changeId={changeId} codes={{}} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={sendBack.isPending}>
            {t('caseSignoff.sendBack')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function waitingLine(workflow: CaseWorkflow, meId: string | null, canSignoff: boolean, t: Translate, time: string): string {
  const name = workflow.signoffRequestedBy?.name ?? '';
  if (meId !== null && workflow.signoffRequestedBy?.id === meId) return t('caseSignoff.waiting.self', { time });
  return t(canSignoff ? 'caseSignoff.waiting.approver' : 'caseSignoff.waiting.viewer', { name, time });
}

function Waiting({ changeId, workflow, canSignoff }: { changeId: string; workflow: CaseWorkflow; canSignoff: boolean }) {
  const t = useT();
  const ctx = useFormatContext();
  const meId = useSession().me?.user.id ?? null;
  const [note, setNote] = useState('');
  const [sendingBack, setSendingBack] = useState(false);
  const approve = useApproveSignoff(changeId, workflow.version);
  const time = workflow.signoffRequestedAt === null ? '' : formatDateTime(workflow.signoffRequestedAt, ctx);
  const line = <p data-signoff-waiting="">{waitingLine(workflow, meId, canSignoff, t, time)}</p>;
  if (!canSignoff) return line;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    approve.mutate({ note: note.trim() });
  };

  // The send-back dialog sits beside the form, never in it: its own submit would
  // otherwise bubble through the React tree into the sign-off.
  return (
    <>
      <form onSubmit={submit} noValidate aria-busy={approve.isPending}>
        {line}
        <Field id="signoff-note" label={t('caseSignoff.note')} hint={t('caseSignoff.noteHint')}>
          <TextArea id="signoff-note" value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
        <ButtonBar>
          <Button variant="outline" onClick={() => setSendingBack(true)}>
            {t('caseSignoff.sendBack')}
          </Button>
          <Button type="submit" disabled={approve.isPending}>
            {t('caseSignoff.approve')}
          </Button>
        </ButtonBar>
        {approve.isError ? (
          <WriteRefusal
            error={approve.error}
            changeId={changeId}
            codes={{
              four_eyes_violation: t('caseSignoff.fourEyes'),
              [STEP_UP_REQUIRED_CODE]: t('caseSignoff.stepUpCancelled'),
            }}
          />
        ) : null}
      </form>
      {sendingBack ? <SendBackModal changeId={changeId} workflow={workflow} requester={workflow.signoffRequestedBy?.name ?? ''} onOpenChange={setSendingBack} /> : null}
    </>
  );
}

function SignedOff({ workflow }: { workflow: CaseWorkflow }) {
  const t = useT();
  const ctx = useFormatContext();
  const rows = [
    {
      label: t('caseSignoff.signedOffBy'),
      person: workflow.signedOffBy,
      at: workflow.closedAt,
    },
    {
      label: t('caseSignoff.askedBy'),
      person: workflow.signoffRequestedBy,
      at: workflow.signoffRequestedAt,
    },
  ];
  return (
    <Panel title={t('caseSignoff.closedHeading')} data-signoff-panel="signed_off">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        {rows.map((row) =>
          row.person === null || row.at === null ? null : (
            <div key={row.label} className="contents">
              <dt className="text-meta text-muted">{row.label}</dt>
              <dd>
                {t('caseSignoff.personOn', {
                  name: row.person.name,
                  date: formatDate(row.at, ctx),
                })}
              </dd>
            </div>
          ),
        )}
      </dl>
    </Panel>
  );
}

export function SignoffPanel({ change, workflow }: CasePanelProps) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  if (workflow.category === 'closed') return closeKindOf(workflow) === 'signed_off' ? <SignedOff workflow={workflow} /> : null;
  if (workflow.category !== 'implementing' && workflow.category !== 'signoff') return null;
  return (
    <Panel title={t('caseSignoff.heading')} data-signoff-panel={workflow.category}>
      {workflow.category === 'implementing' ? (
        <RequestSignoff changeId={change.id} workflow={workflow} canWork={permissions.includes(WORK)} />
      ) : (
        <Waiting changeId={change.id} workflow={workflow} canSignoff={permissions.includes(SIGNOFF)} />
      )}
    </Panel>
  );
}
