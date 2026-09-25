'use client';

import { useRouter } from 'next/navigation';
import { useState, type FormEvent, type ReactNode } from 'react';

import { SupportSessionBanner } from '@/components/shell/SupportSessionBanner';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useAskForSupportAccess, useEnterSupportAccess, useMySupportAccess } from '@/features/console-support-access/hooks';
import type { ConsoleSupportGrant } from '@/features/console-support-access/types';
import { useConsoleTenants } from '@/features/console-tenants/hooks';
import { useFormatContext, useSignOut } from '@/features/identity/hooks';
import { presentSupportGrant } from '@/features/support-access/support-access-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { PUBLIC_HOME } from '@/shared/navigation/registry';
import { formatDateTime } from '@/shared/utils/format';

// Support access, the platform side (design/screens/console-support-access.html,
// TEN-06, D-49, ADR 0042): a platform admin asks one bank for read-only access
// with a purpose, an optional ticket and a window, sees their own requests and
// where each stands, and enters a live one with a passkey (the api client
// opens the prompt on the server's step_up_required). A bank is named by its
// organisation name and a decision by its time: nobody at the bank is named
// here. Entering replaces the console session with the support session, so
// the screen then shows that session and the way out, and reads nothing more.

const DEFAULT_HOURS = 2;

type FormProblem = 'bank' | 'purpose';

function Facts({ children }: { children: ReactNode }) {
  return <dl className="m-0 mt-2 grid gap-x-3.5 gap-y-1.5 text-meta md:grid-cols-[150px_1fr]">{children}</dl>;
}

function Fact({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className={mono ? 'm-0 font-mono' : 'm-0'}>{children}</dd>
    </>
  );
}

function GrantRow({ grant, entering, error, onEnter }: { grant: ConsoleSupportGrant; entering: boolean; error: unknown; onEnter: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-grant-id={grant.id} data-grant-state={grant.state}>
      <PillRow pills={presentSupportGrant(grant, t)} />
      <h3 className="mt-1.5 font-semibold">{grant.tenantName}</h3>
      <Facts>
        <Fact label={t('supportAccess.field.purpose')}>{grant.purpose}</Fact>
        {grant.ticketRef !== '' ? (
          <Fact label={t('supportAccess.field.ticket')} mono>
            {grant.ticketRef}
          </Fact>
        ) : null}
        <Fact label={t('supportAccess.field.askedFor')}>
          {grant.state === 'pending' ? t('console.supportAccess.hoursFromApproval', { hours: grant.hours }) : t('supportAccess.hours', { hours: grant.hours })}
        </Fact>
        <Fact label={t('supportAccess.field.requested')}>{formatDateTime(grant.requestedAt, ctx)}</Fact>
        {grant.decidedAt !== null ? <Fact label={t('supportAccess.field.decided')}>{formatDateTime(grant.decidedAt, ctx)}</Fact> : null}
        {grant.endsAt !== null ? <Fact label={t('supportAccess.field.until')}>{formatDateTime(grant.endsAt, ctx)}</Fact> : null}
      </Facts>
      {grant.state === 'active' ? (
        <>
          <p className="mt-2 text-meta text-muted">{t('console.supportAccess.enterHint')}</p>
          <ProblemAlert error={error} codes={{ step_up_required: t('console.supportAccess.stepUpCancelled'), not_found: t('console.supportAccess.notOpen') }} />
          <ButtonBar>
            <Button size="small" disabled={entering} onClick={onEnter}>
              {entering ? t('console.supportAccess.entering') : t('console.supportAccess.enter')}
            </Button>
          </ButtonBar>
        </>
      ) : null}
    </Row>
  );
}

function AskModal({ open, onClose, onAsked }: { open: boolean; onClose: () => void; onAsked: (grant: ConsoleSupportGrant) => void }) {
  const t = useT();
  const tenants = useConsoleTenants();
  const ask = useAskForSupportAccess();
  const [tenantId, setTenantId] = useState('');
  const [purpose, setPurpose] = useState('');
  const [ticket, setTicket] = useState('');
  const [hours, setHours] = useState(String(DEFAULT_HOURS));
  const [problem, setProblem] = useState<FormProblem | null>(null);
  const banks = (tenants.data?.items ?? []).filter((tenant) => tenant.status === 'active');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (tenantId === '') {
      setProblem('bank');
      return;
    }
    if (purpose.trim() === '') {
      setProblem('purpose');
      return;
    }
    setProblem(null);
    ask.mutate(
      { tenantId, body: { purpose: purpose.trim(), ticketRef: ticket.trim(), hours: Number(hours) } },
      {
        onSuccess: (grant) => {
          onAsked(grant);
          setTenantId('');
          setPurpose('');
          setTicket('');
          setHours(String(DEFAULT_HOURS));
          onClose();
        },
      },
    );
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={t('console.supportAccess.ask')} description={t('console.supportAccess.askBody')}>
      <form onSubmit={submit} noValidate aria-busy={ask.isPending} data-support-request-form="">
        <Field id="support-bank" label={t('console.supportAccess.bank')} error={problem === 'bank' ? t('console.supportAccess.bankRequired') : undefined}>
          <Select id="support-bank" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            <option value="">{t('console.supportAccess.bankPlaceholder')}</option>
            {banks.map((tenant) => (
              <option key={tenant.id} value={tenant.id}>
                {tenant.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          id="support-purpose"
          label={t('supportAccess.field.purpose')}
          hint={t('console.supportAccess.purposeHint')}
          error={problem === 'purpose' ? t('console.supportAccess.purposeRequired') : undefined}
        >
          <TextArea id="support-purpose" value={purpose} placeholder={t('console.supportAccess.purposePlaceholder')} onChange={(e) => setPurpose(e.target.value)} />
        </Field>
        <Field id="support-ticket" label={t('supportAccess.field.ticket')} hint={t('console.supportAccess.ticketHint')}>
          <TextInput id="support-ticket" value={ticket} placeholder={t('console.supportAccess.ticketPlaceholder')} onChange={(e) => setTicket(e.target.value)} />
        </Field>
        <Field id="support-hours" label={t('console.supportAccess.hoursLabel')} hint={t('console.supportAccess.hoursHint')}>
          <TextInput id="support-hours" type="number" min={1} step={1} inputMode="numeric" value={hours} onChange={(e) => setHours(e.target.value)} />
        </Field>
        <p className="text-meta text-muted">{t('console.supportAccess.grantsNothing')}</p>
        {ask.isError ? <ProblemAlert error={ask.error} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={ask.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={ask.isPending}>
            {t('console.supportAccess.ask')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function ConsoleSupportAccessScreen() {
  const t = useT();
  const router = useRouter();
  const [inside, setInside] = useState<ConsoleSupportGrant | null>(null);
  const grants = useMySupportAccess(inside === null);
  const enter = useEnterSupportAccess();
  const leave = useSignOut(() => router.replace(PUBLIC_HOME));
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState<ConsoleSupportGrant | null>(null);
  const [entering, setEntering] = useState<string | null>(null);

  if (inside !== null && inside.endsAt !== null) {
    return (
      <section data-support-session="">
        <SupportSessionBanner tenantName={inside.tenantName} endsAt={inside.endsAt} onLeave={() => leave.mutate()} />
        <p className="text-muted">{t('console.supportAccess.inside', { tenant: inside.tenantName })}</p>
      </section>
    );
  }

  const onEnter = (grant: ConsoleSupportGrant) => {
    setEntering(grant.id);
    enter.mutate(grant.id, { onSuccess: () => setInside(grant) });
  };

  const items = grants.data?.items ?? [];

  return (
    <>
      <PageHead
        title={t('console.supportAccess.title')}
        lede={t('console.supportAccess.lede')}
        actions={<Button onClick={() => setAsking(true)}>{t('console.supportAccess.ask')}</Button>}
      />
      {asked !== null ? <StatusLine tone="positive">{t('console.supportAccess.asked', { tenant: asked.tenantName })}</StatusLine> : null}
      {grants.isPending ? (
        <LoadingState rows={3} />
      ) : grants.isError ? (
        <ErrorState title={t('console.supportAccess.errorTitle')} onRetry={() => void grants.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t('console.supportAccess.emptyTitle')} body={t('console.supportAccess.emptyBody')} />
      ) : (
        <Rows data-support-grants="">
          {items.map((grant) => (
            <GrantRow
              key={grant.id}
              grant={grant}
              entering={entering === grant.id && enter.isPending}
              error={entering === grant.id ? enter.error : null}
              onEnter={() => onEnter(grant)}
            />
          ))}
        </Rows>
      )}
      <AskModal open={asking} onClose={() => setAsking(false)} onAsked={setAsked} />
    </>
  );
}
