'use client';

import Link from 'next/link';
import { useState } from 'react';

import { ScopeControl } from '@/components/inventory/InventoryFilters';
import { searchOf } from '@/components/inventory/InventoryScreen';
import { ListPager } from '@/components/inventory/ListPager';
import { ObligationRow } from '@/components/inventory/ObligationRow';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { Field, TextInput } from '@/components/ui/Field';
import { Fold } from '@/components/ui/fold';
import { Meta, Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, QueryState } from '@/components/ui/States';
import { ToneDot } from '@/components/ui/ToneDot';
import { OBLIGATION_PAGE, useObligations, usePagedObligations, type PerPage } from '@/features/library/hooks';
import { answerFiltersOf, DIRECTIVE_LEVEL, nationalLawsOf, obligationsTitleOf } from '@/features/library/instrument-presentation';
import type { InstrumentDetail, InstrumentLinkRef, Obligation, ObligationQuery, ScopeFilter } from '@/features/library/types';
import type { RegisterInstrumentApplicability } from '@/features/register/api';
import { useInstrumentApplicability } from '@/features/register/hooks';
import { presentCompliance } from '@/features/register/register-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';

// The obligations card of a regulation's page (INV-09, FP-03, FP-04; design/screens/
// tenant-instrument.html): what applies said first, then for a regulation holding duties the
// bank's answers rolled up, the answer filter, a search, the scope and the list a page at a
// time; for a directive, which holds none of its own, each national law that implements it,
// opened in place.

/** The bank's answers and compliance statuses are register facts, read with this permission only. */
const REGISTER_READ = 'register.read';

type Answer = Obligation['applicability'] | null;

export function ObligationsPanel({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const counts = instrument.obligationCounts;
  return (
    <Panel title={obligationsTitleOf(instrument.level.key, t)} data-obligations-panel="">
      {instrument.level.key === DIRECTIVE_LEVEL && counts.inLibrary === 0 ? (
        <NationalLaws instrument={instrument} />
      ) : counts.inLibrary > 0 ? (
        <ObligationList instrument={instrument} />
      ) : counts.waitingForReview === 0 ? (
        <p className="text-meta text-muted">{t('inventory.instrument.applies.none')}</p>
      ) : (
        <Waiting count={counts.waitingForReview} />
      )}
    </Panel>
  );
}

/** New duties under the regulation still in the library's review queue. */
function Waiting({ count }: { count: number }) {
  const t = useT();
  if (count === 0) return null;
  return (
    <p className="mb-3 text-meta text-muted" data-applies-waiting="">
      {t('inventory.instrument.applies.waiting', { count })}
    </p>
  );
}

/** A regulation holding duties: the counts, the roll-up for a reader of the register, then the list. */
function ObligationList({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const rollup = useInstrumentApplicability(instrument.id, permissions.includes(REGISTER_READ));
  const [scope, setScope] = useState<ScopeFilter>('in');
  const [answer, setAnswer] = useState<Answer>(null);
  // The search runs on Enter, as the Inventory's does, never on each key; emptied, it clears at once.
  const [draft, setDraft] = useState('');
  const [q, setQ] = useState('');
  const [perPage, setPerPage] = useState<PerPage>(OBLIGATION_PAGE);
  const [page, setPage] = useState(0);
  const query: ObligationQuery = { instrument: instrument.stableKey };
  if (scope !== 'in') query.footprint = scope;
  if (answer !== null) query.applicability = answer;
  if (q !== '') query.q = q;
  const list = usePagedObligations(query, perPage, page);
  const inventory = `/inventory?${searchOf('obligations', { instrument: instrument.stableKey, regime: '', service: '', dutyType: '', asOf: '', scope, applicability: answer ?? '' })}`;
  // A new filter starts again at the first page.
  const refilter = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setPage(0);
  };
  // The roll-up counts what is in scope only, so its answer filter lives there and nowhere else.
  const onScope = (next: ScopeFilter) => {
    setScope(next);
    if (next !== 'in') setAnswer(null);
    setPage(0);
  };
  const counts = instrument.obligationCounts;

  return (
    <>
      <p className="mb-3 text-body" data-applies-counts="">
        {t('inventory.instrument.applies.counts', { inLibrary: counts.inLibrary, inScope: counts.inScope })}
      </p>
      <Waiting count={counts.waitingForReview} />
      {rollup.isError ? <ProblemAlert error={rollup.error} className="mb-3" /> : null}
      {scope === 'in' && rollup.data !== undefined && rollup.data.inScope > 0 ? (
        <Rollup rollup={rollup.data} answer={answer} onAnswer={refilter(setAnswer)} stableKey={instrument.stableKey} />
      ) : null}
      <div className="flex flex-wrap items-end gap-x-3">
        <form
          role="search"
          className="min-w-[150px] flex-1"
          onSubmit={(event) => {
            event.preventDefault();
            refilter(setQ)(draft.trim());
          }}
        >
          <Field id="instrument-find" label={t('inventory.instrument.find')}>
            <TextInput
              id="instrument-find"
              type="search"
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                if (event.target.value.trim() === '' && q !== '') refilter(setQ)('');
              }}
            />
          </Field>
        </form>
        <div className="mb-3 max-lg:w-full">
          <ScopeControl value={scope} onChange={onScope} />
        </div>
      </div>
      {list.isPending && list.items.length === 0 ? (
        <LoadingState rows={2} />
      ) : list.isError ? (
        <ErrorState title={t('inventory.instrument.obligationsErrorTitle')} onRetry={list.refetch} />
      ) : list.items.length === 0 ? (
        <p className="text-meta text-muted">
          {t(
            answer !== null || query.q !== undefined
              ? 'inventory.instrument.obligationsNoMatch'
              : scope === 'all'
                ? 'inventory.instrument.obligationsEmpty'
                : scope === 'watched'
                  ? 'library.empty.watched.title'
                  : 'inventory.instrument.obligationsEmptyInScope',
          )}
        </p>
      ) : (
        <>
          <div className="grid gap-2">
            {list.items.map((obligation) => (
              <ObligationRow key={obligation.id} obligation={obligation} watched={scope === 'watched'} />
            ))}
          </div>
          <ListPager total={list.total} shown={list.items.length} perPage={perPage} page={page} onPage={setPage} onPerPage={refilter(setPerPage)} />
          <Meta className="mt-3 justify-end">
            <span data-obligations-total="">{t('inventory.count', { count: list.total })}</span>
            <Link href={inventory} prefetch={false} className="underline">
              {t('inventory.instrument.obligationsInInventory')}
            </Link>
          </Meta>
        </>
      )}
    </>
  );
}

/**
 * The bank's answers over the regulation's obligations in scope: the answer filter with its
 * counts, where it applies how the bank complies, and, for a bank of two companies or more,
 * each company's answers with the way to decide what is left. "Applies" and "we comply" stay
 * two facts, each said on its own.
 */
function Rollup({ rollup, answer, onAnswer, stableKey }: { rollup: RegisterInstrumentApplicability; answer: Answer; onAnswer: (answer: Answer) => void; stableKey: string }) {
  const t = useT();
  return (
    <div className="mb-3 grid gap-3" data-rollup="">
      <div role="group" aria-label={t('inventory.instrument.answer.label')} data-answer-filter="">
        <ChipRow>
          {answerFiltersOf(rollup, t).map((filter) => (
            <Chip key={filter.value ?? 'all'} pressed={answer === filter.value} onClick={() => onAnswer(filter.value)}>
              {filter.label}
            </Chip>
          ))}
        </ChipRow>
      </div>
      {rollup.statuses.length === 0 ? null : (
        <div className="flex flex-wrap items-start gap-x-4 gap-y-1 text-meta" data-where-it-applies="">
          <span className="text-muted">{t('inventory.instrument.whereItApplies')}</span>
          {rollup.statuses.map((row) => (
            <span key={row.status.key} className="flex items-start gap-1.5" data-status={row.status.key}>
              <ToneDot tone={presentCompliance(row.status).tone} />
              {t('inventory.instrument.statusCount', { count: row.count, status: row.status.label })}
            </span>
          ))}
        </div>
      )}
      {rollup.companies.length < 2 ? null : (
        <Fold title={t('inventory.instrument.byCompany')} as="h3" data-by-company="">
          <div className="grid gap-2">
            {rollup.companies.map((company) => (
              <div key={company.orgUnit.id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-meta" data-company={company.orgUnit.id}>
                <span className="flex flex-wrap gap-x-2">
                  <span className="font-medium text-fg">{company.orgUnit.name}</span>
                  <span className="text-muted">
                    {t('inventory.instrument.companyCounts', { applies: company.applies, notApplicable: company.notApplicable, underAssessment: company.underAssessment })}
                  </span>
                </span>
                {company.underAssessment === 0 ? null : (
                  <Link href={`/applies?${new URLSearchParams({ company: company.orgUnit.id, instrument: stableKey }).toString()}`} prefetch={false} className="ml-auto underline">
                    {t('inventory.instrument.decide', { count: company.underAssessment })}
                  </Link>
                )}
              </div>
            ))}
          </div>
        </Fold>
      )}
    </div>
  );
}

/**
 * A directive binds the member states, so its duties sit in each national law that implements
 * it: the totals over the laws the library holds, then each law in place, those with duties
 * in the bank's scope first and open.
 */
function NationalLaws({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const { laws, obligations, inScope } = nationalLawsOf(instrument.implementedBy);
  return (
    <div className="grid gap-2 text-body" data-what-applies="">
      <p>{t('inventory.instrument.applies.directive')}</p>
      <Waiting count={instrument.obligationCounts.waitingForReview} />
      {laws.length === 0 ? (
        <p className="text-meta text-muted">{t('inventory.instrument.applies.noNationalLaw')}</p>
      ) : (
        <>
          <p data-national-totals="">{t('inventory.instrument.applies.nationalTotals', { obligations, laws: laws.length, inScope })}</p>
          <div data-implemented-by="">
            {laws.map((law) => (
              <NationalLaw key={law.id} law={law} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function NationalLaw({ law }: { law: InstrumentLinkRef }) {
  const t = useT();
  const counts = law.obligationCounts;
  // The law's name opens its page in one click, outside the toggle; the toggle names the law
  // to a screen reader too. Closed, the content is not rendered, so a law's obligations are
  // read only once it is open.
  return (
    <div className="border-t border-line" data-national-law={law.key}>
      <h3 className="pt-3 text-body font-medium">
        <Link href={`/inventory/instruments/${law.id}`} prefetch={false} className="underline" data-law-link="">
          {law.shortName}
        </Link>
      </h3>
      <Fold
        className="-mt-2 border-t-0"
        defaultOpen={counts.inScope > 0}
        title={
          <>
            <span className="sr-only">{law.shortName} </span>
            <span className="text-meta font-normal text-muted">
              {t('inventory.instrument.lawCounts', { jurisdiction: law.jurisdiction.label, inLibrary: counts.inLibrary, inScope: counts.inScope })}
            </span>
          </>
        }
      >
        <LawObligations law={law} />
      </Fold>
    </div>
  );
}

/** The law's first page of obligations in the bank's scope, as its own page lists them, and the way to all of them there. */
function LawObligations({ law }: { law: InstrumentLinkRef }) {
  const t = useT();
  const obligations = useObligations({ instrument: law.key });
  return (
    <QueryState query={obligations} rows={2} errorTitle={t('inventory.instrument.obligationsErrorTitle')}>
      {(data) => (
        <>
          {data.items.length === 0 ? (
            <p className="text-meta text-muted">{t('inventory.instrument.obligationsEmptyInScope')}</p>
          ) : (
            <div className="grid gap-2">
              {data.items.map((obligation) => (
                <ObligationRow key={obligation.id} obligation={obligation} />
              ))}
            </div>
          )}
          <Meta className="mt-3 justify-end">
            {data.total > data.items.length ? <span data-first-of="">{t('inventory.instrument.firstOf', { shown: data.items.length, total: data.total })}</span> : null}
            {/* The law's page opens on the bank's scope, so the count is what it lists there. */}
            <Link href={`/inventory/instruments/${law.id}`} prefetch={false} className="underline" data-see-all="">
              {t('inventory.instrument.seeAll', { count: law.obligationCounts.inScope })}
            </Link>
          </Meta>
        </>
      )}
    </QueryState>
  );
}
