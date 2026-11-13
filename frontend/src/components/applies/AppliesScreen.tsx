'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type { UseQueryResult } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { DecideDialog, type Answer } from '@/components/applies/DecideDialog';
import { Button } from '@/components/ui/Button';
import { Checkbox, type CheckedState } from '@/components/ui/checkbox';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, TextInput } from '@/components/ui/Field';
import { Fold } from '@/components/ui/fold';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Pager } from '@/components/ui/Pager';
import { Panel } from '@/components/ui/Panel';
import { Pill } from '@/components/ui/Pill';
import { Progress } from '@/components/ui/progress';
import { LoadingState, ProblemAlert } from '@/components/ui/States';
import type { ApplicabilityAnswer, ApplicabilityAnswerPage, ApplicabilityCompany, ApplicabilityRegulation, DecideAll, DecideAllBody } from '@/features/applies/api';
import { useApplicabilityCompanies, useApplicabilityRegulations, useApplicabilityRows, useDecideAll } from '@/features/applies/hooks';
import { basisOf, suggestReason, type Basis, type RegisterRead } from '@/features/applies/suggestion';
import { useFormatContext } from '@/features/identity/hooks';
import { presentApplicability } from '@/features/register/register-presentation';
import { useOrgUnits } from '@/features/tenant-admin/organisation/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination, unlocks } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// What applies (design/screens/tenant-applies.html; REG-01, FP-05, AC-REG1; REG-S22): one
// company at a time, the regulations its licences and the bank's scope bring in, each with
// its obligations, decided all at once, one regulation at a time or row by row through one
// dialog and Decide all, the worker's run with no limit (Alex, 2026-11-12). The address
// carries the company, the open regulation and the filter, so a link opens the same view.
// Why a regulation is listed is a fact about scope and never an answer; a row a colleague
// answered, "Not assessed" with a reason included, is decided and never a target.

/** Regulations and rows on one page (playbook 10's default). */
export const APPLIES_PAGE = 20;
/** The most regulations one read returns: what a decision over all of them stands on. */
const REGULATIONS_MAX = 100;

const FILTERS = ['to_decide', 'decided', 'all'] as const;
export type AppliesFilter = (typeof FILTERS)[number];
const DEFAULT_FILTER: AppliesFilter = 'to_decide';

export function filterFrom(value: string | null): AppliesFilter {
  return FILTERS.find((filter) => filter === value) ?? DEFAULT_FILTER;
}

export interface AppliesView {
  company: string;
  instrument: string | null;
  filter: AppliesFilter;
}

/** The address of a view: the company, the open regulation, and the filter when it is not the default. */
export function appliesSearch(view: AppliesView): string {
  const params = new URLSearchParams({ company: view.company });
  if (view.instrument !== null) params.set('instrument', view.instrument);
  if (view.filter !== DEFAULT_FILTER) params.set('state', view.filter);
  return params.toString();
}

const APPROVE_PERMISSION = 'applicability.approve';

/** The last page that holds anything, for a page a run or a filter emptied. */
const lastPage = (total: number): number => Math.max(0, Math.ceil(total / APPLIES_PAGE) - 1) * APPLIES_PAGE;

export function AppliesScreen() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const companies = useApplicabilityCompanies();
  const units = useOrgUnits();
  const canApprove = (usePermissions() ?? []).includes(APPROVE_PERMISSION);

  const filter = filterFrom(params.get('state'));
  const instrument = params.get('instrument');
  const list = companies.data ?? [];
  const chosen = list.find((company) => company.orgUnit.id === params.get('company')) ?? list.find((company) => company.toDecide > 0) ?? list[0];
  const go = (view: AppliesView) => router.replace(`${pathname}?${appliesSearch(view)}`, { scroll: false });

  const entry = chosen === undefined ? null : (units.data?.find((unit) => unit.id === chosen.orgUnit.id)?.registerEntry ?? null);
  const register: RegisterRead | null = entry === null ? null : { authority: entry.authority.name, readAt: entry.readAt };

  return (
    <>
      <PageHead title={t('applies.title')} />
      {companies.isPending ? (
        <LoadingState rows={3} />
      ) : companies.isError ? (
        <ProblemAlert error={companies.error} />
      ) : chosen === undefined ? (
        <EmptyState title={t('applies.empty.noCompany.title')} body={t('applies.empty.noCompany.body')} action={{ label: t('applies.empty.noCompany.action'), href: '/admin/organisation' }} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {list.length > 1 ? (
              <div role="group" aria-label={t('applies.companies')} className="flex flex-wrap gap-2" data-companies="">
                {list.map((company) => (
                  <Chip key={company.orgUnit.id} pressed={company.orgUnit.id === chosen.orgUnit.id} onClick={() => go({ company: company.orgUnit.id, instrument: null, filter })}>
                    {company.orgUnit.name} <b className="ml-1.5">{company.toDecide}</b> <span className="sr-only">{t('applies.company.toDecide')}</span>
                  </Chip>
                ))}
              </div>
            ) : (
              <h2 className="text-body font-medium">{chosen.orgUnit.name}</h2>
            )}
            <Link href="/admin/licences" className="ml-auto font-medium underline">
              {t('nav.admin.licences')}
            </Link>
          </div>
          <CompanyView
            key={chosen.orgUnit.id}
            company={chosen}
            companies={list}
            register={register}
            canApprove={canApprove}
            filter={filter}
            instrument={instrument}
            go={(patch) => go({ company: chosen.orgUnit.id, instrument, filter, ...patch })}
          />
        </>
      )}
    </>
  );
}

/** What one decision covers, as the dialog says it, and what the start sends beside the answer. */
interface Target {
  covers: string;
  count: number;
  bases: readonly Basis[];
  scope: Pick<DecideAllBody, 'instrument' | 'obligationIds'>;
}

function CompanyView({
  company,
  companies,
  register,
  canApprove,
  filter,
  instrument,
  go,
}: {
  company: ApplicabilityCompany;
  companies: readonly ApplicabilityCompany[];
  register: RegisterRead | null;
  canApprove: boolean;
  filter: AppliesFilter;
  instrument: string | null;
  go: (patch: Partial<AppliesView>) => void;
}) {
  const t = useT();
  const ctx = useFormatContext();
  const canSeeScope = unlocks(findDestination('admin-footprint')?.anyOfPermissions ?? [], usePermissions() ?? []);
  const orgUnitId = company.orgUnit.id;
  const name = company.orgUnit.name;
  // The search reads on Enter, as the regulation page's does, never on each key.
  const [draft, setDraft] = useState('');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  // The rows ticked, each with what brings its regulation into scope; they belong to this company.
  const [ticks, setTicks] = useState<ReadonlyMap<string, Basis>>(new Map());
  const [target, setTarget] = useState<Target | null>(null);
  const [alreadyRunning, setAlreadyRunning] = useState(false);
  // A regulation the person opened or closed; the rest follow the default.
  const [toggled, setToggled] = useState<Readonly<Record<string, boolean>>>({});
  // The regulation the address named on arrival, and whether the page holding it is still sought.
  const [named] = useState(instrument);
  const [seeking, setSeeking] = useState(instrument !== null);
  const scrolled = useRef(false);

  const regulations = useApplicabilityRegulations({ orgUnitId, state: filter === 'all' ? undefined : filter, q: q === '' ? undefined : q, limit: APPLIES_PAGE, offset }, company.offered > 0);
  const counted = useApplicabilityRegulations({ orgUnitId, limit: 1, offset: 0 }, company.offered > 0);
  // What Decide all covers, and what its regulations stand on.
  const toDecide = useApplicabilityRegulations({ orgUnitId, state: 'to_decide', limit: REGULATIONS_MAX, offset: 0 }, canApprove && company.toDecide > 0);
  const decideAll = useDecideAll(canApprove);
  const run = decideAll.run.data;
  const busy = run?.status === 'running' || decideAll.start.isPending;

  const listed = regulations.data;
  const items = listed?.items ?? [];
  const onPage = named !== null && items.some((item) => item.instrument.key === named);
  // The named regulation may sit past this page (a link from the regulation's own page):
  // one read of the first hundred under the filter finds the page that holds it.
  const located = useApplicabilityRegulations(
    { orgUnitId, state: filter === 'all' ? undefined : filter, limit: REGULATIONS_MAX, offset: 0 },
    company.offered > 0 && seeking && listed !== undefined && !onPage,
  ).data;
  if (seeking && listed !== undefined) {
    const at = onPage || located === undefined ? -1 : located.items.findIndex((item) => item.instrument.key === named);
    const holding = Math.floor(at / APPLIES_PAGE) * APPLIES_PAGE;
    if (onPage || (located !== undefined && (at < 0 || holding === offset))) setSeeking(false);
    else if (at >= 0) setOffset(holding);
  }
  // A run or a filter can leave this page empty: step back to the last page that holds anything.
  if (listed !== undefined && listed.items.length === 0 && offset > lastPage(listed.total)) setOffset(lastPage(listed.total));
  // The named regulation starts open; otherwise, once it is no longer sought, the first.
  const opensFirst = onPage ? named : seeking ? undefined : items[0]?.instrument.key;
  const isOpen = (key: string) => toggled[key] ?? key === opensFirst;

  // The regulation the address names starts open and in view, once.
  useEffect(() => {
    if (scrolled.current || !onPage) return;
    scrolled.current = true;
    document.querySelector(`[data-regulation="${named}"]`)?.scrollIntoView({ block: 'start' });
  }, [onPage, named]);

  const page = (next: number) => {
    setSeeking(false);
    setOffset(next);
  };
  const refilter = (next: Partial<AppliesView>) => {
    page(0);
    go(next);
  };

  const open = (next: Target) => {
    decideAll.start.reset();
    setTarget(next);
  };
  const openAll = () => {
    const page = toDecide.data;
    const complete = page !== undefined && page.total <= page.items.length;
    open({
      covers: t('applies.dialog.coversAll', { count: company.toDecide, regulations: page?.total ?? 0 }),
      count: company.toDecide,
      bases: complete ? page.items.map(basisOf) : [],
      scope: {},
    });
  };
  const openRegulation = (regulation: ApplicabilityRegulation) =>
    open({
      covers: t('applies.dialog.coversRegulation', { count: regulation.toDecide, regulation: regulation.instrument.shortName }),
      count: regulation.toDecide,
      bases: [basisOf(regulation)],
      scope: { instrument: regulation.instrument.key },
    });
  const openTicked = () =>
    open({ covers: t('applies.dialog.coversSelected', { count: ticks.size }), count: ticks.size, bases: [...ticks.values()], scope: { obligationIds: [...ticks.keys()] } });

  const submit = (decision: { applicability: Answer; reason: string }) => {
    if (target === null) return;
    decideAll.start.mutate(
      { orgUnitId, ...target.scope, ...decision },
      {
        onSuccess: () => {
          setTarget(null);
          setTicks(new Map());
          setAlreadyRunning(false);
        },
        onError: (error) => {
          if (!hasProblemCode(error, 'decision_running')) return;
          setTarget(null);
          setAlreadyRunning(true);
          void decideAll.run.refetch();
        },
      },
    );
  };
  const tick = (ids: readonly string[], basis: Basis, checked: boolean) => {
    const next = new Map(ticks);
    for (const id of ids) {
      if (checked) next.set(id, basis);
      else next.delete(id);
    }
    setTicks(next);
  };

  if (company.offered === 0) {
    return (
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-body" data-nothing-offered="">
        <p>{t('applies.nothingOffered', { company: name })}</p>
        <Link href="/admin/licences" className="underline">
          {t('nav.admin.licences')}
        </Link>
        {canSeeScope ? (
          <Link href="/admin/footprint" className="underline">
            {t('nav.admin.footprint')}
          </Link>
        ) : null}
      </div>
    );
  }

  const otherCompany = run === undefined || run.orgUnitId === null || run.orgUnitId === orgUnitId ? null : (companies.find((row) => row.orgUnit.id === run.orgUnitId)?.orgUnit.name ?? null);
  const allDecided = filter === 'to_decide' && q === '' && company.toDecide === 0;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="text-body" data-applies-summary="">
          {counted.data === undefined
            ? t('applies.summary.toDecide', { count: company.toDecide })
            : t('applies.summary', { offered: company.offered, regulations: counted.data.total, toDecide: company.toDecide })}
        </p>
        {canApprove && company.toDecide > 0 ? (
          <Button className="ml-auto" disabled={busy || toDecide.data === undefined} onClick={openAll} data-decide-all="">
            {t('applies.decideAll', { count: company.toDecide })}
          </Button>
        ) : null}
      </div>

      {alreadyRunning && run?.status === 'running' ? <Notice data-decide-already="">{t('applies.run.already')}</Notice> : null}
      {run === undefined ? null : <RunPanel run={run} otherCompany={otherCompany} />}

      <div className="mb-3 flex flex-wrap items-end gap-x-3 gap-y-2">
        <div role="group" aria-label={t('applies.filter.label')} className="mb-3">
          <ChipRow>
            <Chip pressed={filter === 'to_decide'} onClick={() => refilter({ filter: 'to_decide' })}>
              {t('applies.filter.toDecide', { count: company.toDecide })}
            </Chip>
            <Chip pressed={filter === 'decided'} onClick={() => refilter({ filter: 'decided' })}>
              {t('applies.filter.decided', { count: company.offered - company.toDecide })}
            </Chip>
            <Chip pressed={filter === 'all'} onClick={() => refilter({ filter: 'all' })}>
              {t('applies.filter.all', { count: company.offered })}
            </Chip>
          </ChipRow>
        </div>
        <form
          role="search"
          className="ml-auto min-w-[200px] flex-1 sm:max-w-[30rem]"
          onSubmit={(event) => {
            event.preventDefault();
            page(0);
            setQ(draft.trim());
          }}
        >
          <Field id="applies-find" label={t('applies.find')}>
            <TextInput
              id="applies-find"
              type="search"
              value={draft}
              placeholder={t('applies.findPlaceholder')}
              onChange={(event) => {
                setDraft(event.target.value);
                if (event.target.value.trim() === '' && q !== '') {
                  page(0);
                  setQ('');
                }
              }}
            />
          </Field>
        </form>
      </div>

      {allDecided ? (
        <EmptyState
          title={t('applies.allDecided.title', { company: name })}
          action={{ label: t('applies.allDecided.action'), href: `/applies?${appliesSearch({ company: orgUnitId, instrument: null, filter: 'decided' })}` }}
        />
      ) : regulations.isPending ? (
        <LoadingState rows={3} />
      ) : regulations.isError ? (
        <ProblemAlert error={regulations.error} />
      ) : items.length === 0 ? (
        <p className="text-meta text-muted" data-no-regulation="">
          {q !== '' ? t('applies.noMatch') : filter === 'decided' ? t('applies.noneDecided', { company: name }) : t('applies.rows.empty')}
        </p>
      ) : (
        <Panel className="py-1" data-regulations="">
          {items.map((regulation) => (
            <RegulationLine
              // A new filter starts the regulation's rows on their first page.
              key={`${filter}:${regulation.instrument.key}`}
              regulation={regulation}
              orgUnitId={orgUnitId}
              filter={filter}
              open={isOpen(regulation.instrument.key)}
              onOpenChange={(next) => {
                setToggled({ ...toggled, [regulation.instrument.key]: next });
                if (next) go({ instrument: regulation.instrument.key });
              }}
              canApprove={canApprove}
              busy={busy}
              onDecide={() => openRegulation(regulation)}
              ticks={ticks}
              onTick={tick}
            />
          ))}
          {regulations.data.total > APPLIES_PAGE ? (
            <Pager className="mb-3" offset={offset} limit={APPLIES_PAGE} shown={items.length} total={regulations.data.total} onOffset={page} />
          ) : null}
        </Panel>
      )}

      {ticks.size > 0 ? (
        <div
          role="region"
          aria-label={t('applies.selection')}
          className="sticky bottom-[calc(var(--tabbar-top)+8px)] z-10 mt-4 flex flex-wrap items-center gap-3 rounded-card border border-line-strong bg-surface px-4 py-3"
          data-selection-bar=""
        >
          <span role="status">{t('applies.selected', { count: ticks.size })}</span>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="ghost" size="small" onClick={() => setTicks(new Map())}>
              {t('applies.clear')}
            </Button>
            <Button size="small" disabled={busy} onClick={openTicked}>
              {t('inventory.instrument.decide', { count: ticks.size })}
            </Button>
          </div>
        </div>
      ) : null}

      {target === null ? null : (
        <DecideDialog
          company={name}
          covers={target.covers}
          count={target.count}
          suggestion={suggestReason(target.bases, name, register, t, ctx)}
          pending={decideAll.start.isPending}
          error={decideAll.start.isError && !hasProblemCode(decideAll.start.error, 'decision_running') ? decideAll.start.error : undefined}
          codes={{ not_found: t('applies.dialog.notFound') }}
          onSubmit={submit}
          onClose={() => setTarget(null)}
        />
      )}
    </>
  );
}

function RegulationLine({
  regulation,
  orgUnitId,
  filter,
  open,
  onOpenChange,
  canApprove,
  busy,
  onDecide,
  ticks,
  onTick,
}: {
  regulation: ApplicabilityRegulation;
  orgUnitId: string;
  filter: AppliesFilter;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canApprove: boolean;
  busy: boolean;
  onDecide: () => void;
  ticks: ReadonlyMap<string, Basis>;
  onTick: (ids: readonly string[], basis: Basis, checked: boolean) => void;
}) {
  const t = useT();
  const { instrument, through } = regulation;
  // Rows are read only while the regulation is open, a page at a time.
  const [offset, setOffset] = useState(0);
  const rows = useApplicabilityRows({ orgUnitId, instrument: instrument.key, state: filter === 'all' ? undefined : filter, limit: APPLIES_PAGE, offset }, open);
  // A run can leave this page empty: step back to the last page that holds anything.
  if (rows.data !== undefined && rows.data.items.length === 0 && offset > lastPage(rows.data.total)) setOffset(lastPage(rows.data.total));
  const basis = basisOf(regulation);
  // The line's box ticks every row to decide on the open page; mixed when only some are.
  const targets = open ? (rows.data?.items ?? []).filter((row) => row.decidedBy === null).map((row) => row.obligationId) : [];
  const tickedHere = targets.filter((id) => ticks.has(id)).length;
  const all: CheckedState = tickedHere === 0 ? false : tickedHere === targets.length ? true : 'indeterminate';
  const why = through.lines.length > 0 ? t('applies.through.licence', { count: through.lines.length, lines: through.lines.join(', ') }) : t('applies.through.scope', { term: through.term.label });
  // The regulation's name opens its page in one click, outside the fold's toggle, as the
  // regulation page places a national law's name; the toggle names it to a screen reader too.
  return (
    <div className="border-t border-line first:border-t-0" data-regulation={instrument.key}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-3">
        {!canApprove ? null : targets.length > 0 ? (
          <Checkbox checked={all} onCheckedChange={(checked) => onTick(targets, basis, checked)} aria-label={t('applies.selectAll', { regulation: instrument.shortName })} data-select-all="" />
        ) : (
          <span aria-hidden="true" className="size-5 shrink-0" />
        )}
        <h2 className="text-body font-medium">
          <Link href={`/inventory/instruments/${instrument.id}`} prefetch={false} className="underline" data-regulation-link="">
            {instrument.shortName}
          </Link>
        </h2>
        {canApprove && regulation.toDecide > 0 ? (
          <Button variant="outline" size="small" className="ml-auto" disabled={busy} onClick={onDecide} data-decide-regulation="">
            {t('inventory.instrument.decide', { count: regulation.toDecide })}
          </Button>
        ) : null}
      </div>
      <Fold
        className="border-t-0"
        open={open}
        onOpenChange={onOpenChange}
        title={
          <>
            <span className="sr-only">{instrument.shortName}</span>{' '}
            <span className="flex flex-wrap gap-x-3 text-meta font-normal text-muted">
              <span>{why}</span>{' '}
              <span data-regulation-count="">{t('applies.regulation.count', { toDecide: regulation.toDecide, offered: regulation.offered })}</span>
            </span>
          </>
        }
      >
        <RegulationRows rows={rows} offset={offset} onOffset={setOffset} regulation={regulation} canApprove={canApprove} ticks={ticks} onTick={(id, checked) => onTick([id], basis, checked)} />
      </Fold>
    </div>
  );
}

/** An open regulation's rows, as its line read them while open. */
function RegulationRows({
  rows,
  offset,
  onOffset,
  regulation,
  canApprove,
  ticks,
  onTick,
}: {
  rows: UseQueryResult<ApplicabilityAnswerPage>;
  offset: number;
  onOffset: (offset: number) => void;
  regulation: ApplicabilityRegulation;
  canApprove: boolean;
  ticks: ReadonlyMap<string, Basis>;
  onTick: (id: string, checked: boolean) => void;
}) {
  const t = useT();
  if (rows.isPending) return <LoadingState rows={2} />;
  if (rows.isError) return <ProblemAlert error={rows.error} />;
  if (rows.data.items.length === 0) return <p className="text-meta text-muted">{t('applies.rows.empty')}</p>;
  return (
    <div data-rows="">
      {rows.data.items.map((row) => (
        <RowLine
          key={row.obligationId}
          row={row}
          regulation={regulation}
          canApprove={canApprove}
          ticked={ticks.has(row.obligationId)}
          onTick={(checked) => onTick(row.obligationId, checked)}
        />
      ))}
      {rows.data.total > APPLIES_PAGE ? <Pager offset={offset} limit={APPLIES_PAGE} shown={rows.data.items.length} total={rows.data.total} onOffset={onOffset} /> : null}
    </div>
  );
}

function RowLine({ row, regulation, canApprove, ticked, onTick }: { row: ApplicabilityAnswer; regulation: ApplicabilityRegulation; canApprove: boolean; ticked: boolean; onTick: (checked: boolean) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const titleId = `applies-row-${row.obligationId}`;
  const own = regulation.through.term;
  const covers = row.matchedTerms.filter((term) => !(term.dimension === own.dimension && term.key === own.key));
  const decided = row.decidedBy;
  const pill = presentApplicability(row.applicability, t);
  return (
    <div className="flex items-start gap-3 border-t border-line py-2.5" data-row={row.obligationId} data-to-decide={decided === null ? '' : undefined}>
      {!canApprove ? null : decided === null ? (
        <Checkbox checked={ticked} onCheckedChange={onTick} aria-labelledby={titleId} />
      ) : (
        <span aria-hidden="true" className="size-5 shrink-0" />
      )}
      <div className="grid min-w-0 flex-1 gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="grid min-w-0 gap-x-2.5 sm:grid-cols-[7rem_minmax(0,1fr)]">
          <span className="font-mono text-meta text-muted">{row.refLabel}</span>
          <Link id={titleId} href={`/inventory/obligations/${row.obligationId}`} prefetch={false} className="underline">
            {row.title === '' ? row.refLabel : row.title}
          </Link>
        </div>
        <div className="text-meta text-muted sm:text-right" data-row-state="">
          {decided === null ? (
            t('applies.row.toDecide')
          ) : (
            <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
              <Pill tone={pill.tone}>{pill.label}</Pill>
              <span>{row.decidedAt === null ? decided.name : t('applies.row.decidedBy', { name: decided.name, date: formatDate(row.decidedAt, ctx) })}</span>
            </span>
          )}
        </div>
        {covers.length > 0 ? (
          <p className="text-meta text-muted sm:col-span-2" data-covers="">
            {t('applies.row.covers', { terms: covers.map((term) => term.label).join(', ') })}
          </p>
        ) : null}
      </div>
    </div>
  );
}

// The run panel: progress while the worker works, then what it did, until Done hides
// that run, here and on the next visit (a per-viewer convenience: the run's start time
// is kept in this browser, and the page shows the run whenever it cannot be read).
const DISMISSED_KEY = 'applies.decide-all.dismissed';

function readDismissed(): string | null {
  try {
    return window.localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

function writeDismissed(key: string): void {
  try {
    window.localStorage.setItem(DISMISSED_KEY, key);
  } catch {
    // Storage refused: the run stays hidden for this visit only.
  }
}

const STOPPED: Readonly<Record<NonNullable<DecideAll['stopped']>, MessageKey>> = {
  permission_revoked: 'applies.run.stopped.permissionRevoked',
  membership_ended: 'applies.run.stopped.membershipEnded',
  reason_expired: 'applies.run.stopped.reasonExpired',
  failed: 'applies.run.stopped.failed',
};

function RunPanel({ run, otherCompany }: { run: DecideAll; otherCompany: string | null }) {
  const t = useT();
  const [dismissed, setDismissed] = useState<string | null>(readDismissed);
  const key = run.startedAt ?? run.updatedAt ?? '';
  if (run.status === 'idle' || (run.status === 'finished' && dismissed === key)) return null;
  const answer = run.applicability === null ? '' : presentApplicability(run.applicability, t).label;
  const done = run.set + run.skipped + run.refused;
  return (
    <Panel data-decide-run={run.status}>
      {otherCompany === null ? null : <p className="text-meta text-muted">{t('applies.run.company', { company: otherCompany })}</p>}
      {run.status === 'running' ? (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <p role="status" className="font-medium">
              {t('applies.run.running', { total: run.total, answer })}
            </p>
            <span className="text-meta text-muted" data-run-count="">
              {t('applies.run.progress', { done, total: run.total })}
            </span>
          </div>
          <Progress className="mt-2" value={done} max={run.total} aria-label={t('applies.run.progressLabel')} />
        </>
      ) : (
        <>
          <p role="status" className="font-medium" data-run-result="">
            {t('applies.run.set', { count: run.set, answer })}
          </p>
          {run.skipped > 0 ? <p className="mt-1">{t('applies.run.skipped', { count: run.skipped })}</p> : null}
          {run.stopped === null ? null : <p className="mt-1">{t(STOPPED[run.stopped])}</p>}
          {run.refused > 0 ? (
            <Fold className="mt-2" title={t('applies.run.refused', { count: run.refused })} data-run-refused="">
              <ul className="m-0 grid list-none gap-1 p-0">
                {run.refusals.map((refusal) => (
                  <li key={refusal.obligationId} data-refusal={refusal.obligationId}>
                    {refusal.title === '' ? null : <b>{refusal.title} </b>}
                    <span className="text-meta text-muted">{refusal.detail}</span>
                  </li>
                ))}
              </ul>
            </Fold>
          ) : null}
          <Button
            variant="ghost"
            size="small"
            className="mt-2"
            onClick={() => {
              writeDismissed(key);
              setDismissed(key);
            }}
          >
            {t('common.done')}
          </Button>
        </>
      )}
    </Panel>
  );
}
