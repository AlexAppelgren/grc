'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { Facts, type Fact } from '@/components/inventory/ObligationPanels';
import { GapAcceptancePanel } from '@/components/register/GapAcceptancePanel';
import { GapForm } from '@/components/register/GapForm';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useObligationTitle } from '@/features/gaps/hooks';
import { gapActions, gapPills, isWaiting, ownerName, targetLine } from '@/features/gaps/gap-view';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useGaps } from '@/features/register/hooks';
import type { RegisterGap, RegisterGapQuery } from '@/features/register/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import { formatDateTime } from '@/shared/utils/format';

// /gaps (design/screens/tenant-gaps.html; REG-03): every gap the bank has
// recorded, across the register, by target date. The filters keep their keys
// in the address so a filtered list can be shared, and each row opens its
// record in place. The record is the same on the obligation page.

const PAGE = 20;

/** The pills, the title and the facts line of one gap, on the list and on the obligation page. */
export function GapSummary({ gap, withObligation, expanded, onToggle }: { gap: RegisterGap; withObligation: boolean; expanded: boolean; onToggle: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const obligationTitle = useObligationTitle(gap);
  const target = targetLine(gap, new Date(), t, ctx);
  return (
    <>
      <div className="mb-1.5">
        <PillRow pills={gapPills(gap)} />
      </div>
      <h3 className="m-0">
        <button type="button" className="text-left font-semibold underline-offset-[3px] hover:underline" aria-expanded={expanded} onClick={onToggle} data-gap-toggle="">
          {gap.title}
        </button>
      </h3>
      {withObligation && obligationTitle !== null ? <p className="mt-0.5 mb-1 text-muted">{obligationTitle}</p> : null}
      <Meta className="mt-1">
        <span>{ownerName(gap, t)}</span>
        <span className={cn(target.overdue && 'font-medium text-negative')} data-target-line="">
          {target.text}
        </span>
        {isWaiting(gap) ? <span data-waiting-meta="">{t('gaps.row.waiting')}</span> : null}
      </Meta>
    </>
  );
}

/** The record: what is missing, the plan and the way out, with the last action's outcome announced above them. */
export function GapRecord({ gap, withObligation, wide }: { gap: RegisterGap; withObligation: boolean; wide: boolean }) {
  const t = useT();
  const ctx = useFormatContext();
  const meId = useSession().me?.user.id ?? null;
  const permissions = usePermissions() ?? [];
  const obligationTitle = useObligationTitle(gap);
  const [message, setMessage] = useState<MessageKey | null>(null);
  const [editing, setEditing] = useState(false);
  const target = targetLine(gap, new Date(), t, ctx);

  const facts: Fact[] = [];
  if (withObligation) {
    facts.push({
      key: 'obligation',
      label: t('gaps.record.obligation'),
      value: (
        <Link href={`/inventory/obligations/${gap.obligationId}`} prefetch={false} className="underline">
          {obligationTitle ?? t('gaps.record.obligation')}
        </Link>
      ),
    });
  }
  facts.push(
    { key: 'entity', label: t('gaps.record.entity'), value: t(gap.orgUnitId === null ? 'gaps.record.wholeObligation' : 'gaps.record.oneEntity') },
    { key: 'identified', label: t('gaps.record.identified'), value: t('gaps.record.identifiedBy', { date: formatDateTime(gap.identifiedAt, ctx), name: gap.identifiedBy.name }) },
    { key: 'owner', label: t('gaps.record.owner'), value: ownerName(gap, t) },
    { key: 'target', label: t('gaps.record.target'), value: <span className={cn(target.overdue && 'text-negative')}>{target.text}</span> },
  );

  return (
    <div className="mt-3" data-gap-record={gap.id}>
      <p role="status" tabIndex={-1} className={cn('font-medium', message !== null && 'mb-3')} data-gap-status-line="">
        {message === null ? null : t(message)}
      </p>
      <div className={cn('grid gap-x-4', wide && 'lg:grid-cols-[3fr_2fr]')}>
        <div>
          <Panel title={t('gaps.record.missingTitle')}>
            <p className="mb-3 whitespace-pre-line">{gap.description ?? t('gaps.record.noDescription')}</p>
            <Facts facts={facts} />
            {gapActions(gap, meId, permissions).edit ? (
              <ButtonBar>
                <Button variant="outline" size="small" onClick={() => setEditing(true)}>
                  {t('gaps.record.edit')}
                </Button>
              </ButtonBar>
            ) : null}
          </Panel>
          <Panel title={t('gaps.record.planTitle')}>
            <p className="whitespace-pre-line" data-gap-plan="">
              {gap.remediation ?? t('gaps.record.noPlan')}
            </p>
          </Panel>
        </div>
        <div>
          <GapAcceptancePanel gap={gap} onDone={setMessage} />
        </div>
      </div>
      {editing ? (
        <GapForm
          obligationId={gap.obligationId}
          obligationTitle={obligationTitle ?? ''}
          gap={gap}
          onClose={() => setEditing(false)}
          onDone={() => {
            setEditing(false);
            setMessage('gaps.done.saved');
          }}
        />
      ) : null}
    </div>
  );
}

function filtersFrom(params: URLSearchParams, meId: string | null): RegisterGapQuery {
  const filters: RegisterGapQuery = {};
  const status = params.get('status');
  const severity = params.get('severity');
  const targetTo = params.get('targetTo');
  if (status) filters.status = status;
  if (severity) filters.severity = severity;
  if (params.get('owner') === 'me' && meId !== null) filters.owner = meId;
  if (targetTo) filters.targetTo = targetTo;
  return filters;
}

function GapFilters({ onChange }: { onChange: (name: string, value: string) => void }) {
  const t = useT();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const statuses = useVocabularyValues('gap_status');
  const severities = useVocabularyValues('risk_rating');
  const select = (name: string, label: MessageKey, any: MessageKey, rows: readonly { key: string; label: string }[]) => (
    <label className="grid min-w-0 gap-1 text-meta text-muted">
      {t(label)}
      <Select value={params.get(name) ?? ''} onChange={(e) => onChange(name, e.target.value)} data-gap-filter={name}>
        <option value="">{t(any)}</option>
        {rows.map((row) => (
          <option key={row.key} value={row.key}>
            {row.label}
          </option>
        ))}
      </Select>
    </label>
  );
  return (
    <form role="search" aria-label={t('gaps.filters.label')} className="mb-4 grid grid-cols-2 items-end gap-2 lg:grid-cols-5" onSubmit={(e) => e.preventDefault()}>
      {select('status', 'gaps.filters.status', 'gaps.filters.anyStatus', statuses.data ?? [])}
      {select('severity', 'gaps.filters.severity', 'gaps.filters.anySeverity', severities.data ?? [])}
      {select('owner', 'gaps.filters.owner', 'gaps.filters.anyone', [{ key: 'me', label: t('gaps.filters.me') }])}
      <label className="grid min-w-0 gap-1 text-meta text-muted">
        {t('gaps.filters.targetBy')}
        <TextInput type="date" value={params.get('targetTo') ?? ''} onChange={(e) => onChange('targetTo', e.target.value)} data-gap-filter="targetTo" />
      </label>
      <Button variant="ghost" className="self-end" onClick={() => router.replace(pathname)}>
        {t('gaps.filters.clear')}
      </Button>
    </form>
  );
}

export function GapsScreen() {
  const t = useT();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const meId = useSession().me?.user.id ?? null;

  const go = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    for (const [name, value] of Object.entries(changes)) {
      if (value === '' || value === '0') next.delete(name);
      else next.set(name, value);
    }
    const query = next.toString();
    router.replace(query === '' ? pathname : `${pathname}?${query}`);
  };

  return (
    <div data-gaps-screen="">
      <PageHead title={t('gaps.title')} lede={t('gaps.lede')} />
      <GapFilters onChange={(name, value) => go({ [name]: value, page: '' })} />
      {/* "Me" is a person's id, so the list waits for the session rather than asking for everyone's first. */}
      {params.get('owner') === 'me' && meId === null ? <LoadingState rows={3} /> : <GapList params={params} meId={meId} onPage={(page) => go({ page: String(page) })} />}
    </div>
  );
}

function GapList({ params, meId, onPage }: { params: URLSearchParams; meId: string | null; onPage: (page: number) => void }) {
  const t = useT();
  const pathname = usePathname();
  const page = Math.max(0, Number(params.get('page') ?? '0') || 0);
  const gaps = useGaps(filtersFrom(params, meId), { limit: PAGE, offset: page * PAGE });
  const [open, setOpen] = useState<string | null>(null);
  const filtered = ['status', 'severity', 'owner', 'targetTo'].some((name) => params.get(name));

  if (gaps.isPending) return <LoadingState rows={3} />;
  if (gaps.isError) return <ErrorState title={t('gaps.errorTitle')} onRetry={() => void gaps.refetch()} />;
  const { items, total } = gaps.data;
  if (total === 0) {
    return filtered ? (
      <EmptyState title={t('gaps.noMatch.title')} body={t('gaps.noMatch.body')} action={{ label: t('gaps.filters.clear'), href: pathname }} />
    ) : (
      <EmptyState title={t('gaps.empty.title')} body={t('gaps.empty.body')} action={{ label: t('gaps.empty.action'), href: '/inventory' }} />
    );
  }
  return (
    <>
      <p className="mb-2 text-meta text-muted tabular-nums" data-gap-count="">
        {t('gaps.count', { count: total })}
      </p>
      <Rows data-gap-rows="">
        {items.map((gap) => (
          <Row key={gap.id} data-gap={gap.id} data-gap-status={gap.status.kind ?? undefined}>
            <GapSummary gap={gap} withObligation expanded={open === gap.id} onToggle={() => setOpen(open === gap.id ? null : gap.id)} />
            {open === gap.id ? <GapRecord gap={gap} withObligation wide /> : null}
          </Row>
        ))}
      </Rows>
      {total > PAGE ? (
        <ButtonBar>
          <Button variant="outline" size="small" disabled={page === 0} onClick={() => onPage(page - 1)}>
            {t('gaps.pager.previous')}
          </Button>
          <Button variant="outline" size="small" disabled={(page + 1) * PAGE >= total} onClick={() => onPage(page + 1)}>
            {t('gaps.pager.next')}
          </Button>
        </ButtonBar>
      ) : null}
    </>
  );
}
