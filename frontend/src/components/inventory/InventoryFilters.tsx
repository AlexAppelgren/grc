'use client';

import { useState, type ReactNode } from 'react';

import { NavIcon } from '@/components/shell/NavIcon';
import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { TextInput } from '@/components/ui/Field';
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { useFootprint, useTerms } from '@/features/footprint/hooks';
import type { TaxonomyTerm } from '@/features/footprint/types';
import { INSTRUMENT_OPTIONS, useInstruments } from '@/features/library/hooks';
import type { ScopeFilter } from '@/features/library/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// The inventory's filters (design/screens/tenant-inventory.html, D-103): a Filters
// sheet, the set filters as removable chips beside its button, and the scope as a
// segmented control on the tab row. Regime and Service are taxonomy terms, Duty type
// is a library vocabulary, Instrument a stable key from GET /instruments; every value
// carries the row's key and shows the row's label, so a rename never changes what a
// filter means. The values follow the scope: a filter never offers what the scope
// would hide anyway.

export const REGIME = 'regime';
export const SERVICE = 'service_type';
export const DUTY_TYPE = 'duty_type';

/** What the screen filters by, all keys and a plain date; never a label. */
export interface InventoryFilters {
  instrument: string;
  regime: string;
  service: string;
  dutyType: string;
  /** A plain date, YYYY-MM-DD; empty means today where the tenant is. */
  asOf: string;
  scope: ScopeFilter;
}

/** The Instruments tab's own filters: GET /instruments takes only regime, q and footprint (chunk3-rest default). */
export interface InstrumentFilters {
  regime: string;
  scope: ScopeFilter;
}

export const SCOPE_VALUES: readonly ScopeFilter[] = ['in', 'watched', 'all'];

/**
 * The regulatory scope (FP-03, FP-04): one value of three, so exactly one segment is
 * chosen and no contradictory pair can be sent. The inventory's two tabs and the
 * instrument card's obligations use it alike (foundations.md "Segmented control").
 */
export function ScopeControl({ value, onChange }: { value: ScopeFilter; onChange: (next: ScopeFilter) => void }) {
  const t = useT();
  const label: Record<ScopeFilter, string> = { in: t('library.scope.in'), watched: t('library.scope.watched'), all: t('library.scope.all') };
  return (
    <div role="group" aria-label={t('library.scope.label')} className="flex gap-0.5 rounded-card border border-line-control bg-surface p-0.5 max-lg:w-full">
      {SCOPE_VALUES.map((scope) => (
        <button
          key={scope}
          type="button"
          aria-pressed={value === scope}
          onClick={() => onChange(scope)}
          className={cn(
            'h-7 flex-1 rounded-control border px-3 text-meta font-medium whitespace-nowrap lg:flex-none',
            value === scope ? 'border-line-strong bg-neutral-soft text-fg' : 'border-transparent text-muted hover:text-fg',
          )}
        >
          {label[scope]}
        </button>
      ))}
    </div>
  );
}

/**
 * A dimension's values for a filter: the terms the bank's regulatory scope chose, or
 * every term when the scope is lifted or the dimension restricts nothing (it does not
 * restrict, every term is chosen, or none is, which `taxonomy_in_footprint` reads as
 * no restriction). "Markets we watch" widens only jurisdictions, so it keeps the
 * scope's terms here.
 */
function useScopedTerms(dimension: string, scope: ScopeFilter): { all: TaxonomyTerm[]; offered: TaxonomyTerm[] } {
  const all = useTerms(dimension).data ?? [];
  const chosen = useFootprint().data?.dimensions.find((row) => row.dimension.key === dimension);
  if (scope === 'all' || chosen === undefined || !chosen.restrictsFootprint || chosen.allSelected || chosen.terms.length === 0) {
    return { all, offered: all };
  }
  const keys = new Set(chosen.terms.map((term) => term.key));
  return { all, offered: all.filter((term) => keys.has(term.key)) };
}

/**
 * The instruments with obligations inside the scope, at the route's maximum page, each
 * with its count (INV-01). Read only while the picker is open or an instrument is set,
 * so the list never asks for a hundred instruments it does not show (NFR-02).
 */
function useInstrumentOptions(scope: ScopeFilter, enabled = true) {
  return useInstruments(scope === 'in' ? {} : { footprint: scope }, INSTRUMENT_OPTIONS, enabled);
}

/**
 * The name of the instrument in the URL. One outside the scope's options is named from
 * the options outside it, read only then; the key shows only while that read loads, or
 * for an instrument past the hundredth or unknown, so a chip never reads blank.
 */
function useInstrumentName(key: string, scope: ScopeFilter): string {
  const options = useInstrumentOptions(scope, key !== '');
  const listed = options.data?.items.find((instrument) => instrument.stableKey === key);
  const outside = useInstruments({ footprint: 'all' }, INSTRUMENT_OPTIONS, key !== '' && options.isSuccess && listed === undefined && scope !== 'all');
  return listed?.shortName ?? outside.data?.items.find((instrument) => instrument.stableKey === key)?.shortName ?? key;
}

/** One filter's values as toggles: at most one on, and pressing the on one clears it (foundations.md "Filters sheet"). */
function ToggleGroup({ label, values, value, onChange }: { label: string; values: { key: string; label: string }[]; value: string; onChange: (next: string) => void }) {
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0">
      <legend className="microlabel mb-2 text-muted">{label}</legend>
      <ChipRow>
        {values.map((row) => (
          <Chip key={row.key} pressed={value === row.key} onClick={() => onChange(value === row.key ? '' : row.key)}>
            {row.label}
          </Chip>
        ))}
      </ChipRow>
    </fieldset>
  );
}

/** The Instrument filter: a search over rows, since the list is long, each with its obligation count. */
function InstrumentPicker({ value, scope, onChange }: { value: string; scope: ScopeFilter; onChange: (next: string) => void }) {
  const t = useT();
  const [find, setFind] = useState('');
  const wanted = find.trim().toLocaleLowerCase();
  const options = (useInstrumentOptions(scope).data?.items ?? []).filter((instrument) => wanted === '' || instrument.shortName.toLocaleLowerCase().includes(wanted));
  const row = (key: string, name: string, count?: number) => (
    <button
      key={key}
      type="button"
      aria-pressed={value === key}
      aria-label={count === undefined ? undefined : t('inventory.filter.instrumentOption', { name, count })}
      onClick={() => onChange(key)}
      className={cn('flex min-h-9 w-full items-center justify-between gap-2 rounded-control px-2.5 text-left hover:hover-fill', value === key && 'bg-neutral-soft font-medium')}
    >
      <span>{name}</span>
      {count === undefined ? null : <span className="text-meta text-muted">{count}</span>}
    </button>
  );
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0">
      <legend className="microlabel mb-2 text-muted">{t('inventory.filter.instrument')}</legend>
      <TextInput type="search" aria-label={t('inventory.filters.findInstrument')} placeholder={t('inventory.filters.findInstrument')} value={find} onChange={(event) => setFind(event.target.value)} />
      <div className="mt-1.5 grid max-h-64 gap-0.5 overflow-y-auto" data-instrument-options="">
        {row('', t('inventory.filter.allInstruments'))}
        {options.map((instrument) => row(instrument.stableKey, instrument.shortName, instrument.obligationCount))}
      </div>
    </fieldset>
  );
}

/**
 * The Filters button and its sheet: from the right edge on a desktop and from the bottom
 * on a phone. A change applies at once, so Done only closes the sheet.
 */
function FilterSheet({ onClear, children }: { onClear: () => void; children: ReactNode }) {
  const t = useT();
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" data-filters-button="">
          <NavIcon id="filters" />
          {t('inventory.filters.open')}
        </Button>
      </SheetTrigger>
      <SheetContent side="end" data-filters-sheet="">
        <div className="flex items-center justify-between gap-2 py-1 pr-2 pl-4 lg:pl-6">
          <SheetTitle>{t('inventory.filters.title')}</SheetTitle>
          <SheetClose aria-label={t('inventory.filters.close')} className="inline-flex size-11 items-center justify-center rounded-control text-fg hover:hover-fill">
            <NavIcon id="close" size="tab" />
          </SheetClose>
        </div>
        <p className="border-b border-line px-4 pb-3 text-meta text-muted lg:px-6">{t('inventory.filters.scopeHint')}</p>
        <div className="grid min-h-0 flex-1 content-start gap-5 overflow-y-auto px-4 py-4 lg:px-6">{children}</div>
        <div className="flex justify-end gap-2 border-t border-line px-4 pt-3 lg:px-6">
          <Button variant="outline" onClick={onClear}>
            {t('inventory.filters.clearAll')}
          </Button>
          <SheetClose asChild>
            <Button>{t('inventory.filters.done')}</Button>
          </SheetClose>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** A set filter beside the Filters button: its value, and a Remove labelled with the filter and the value. */
function SetFilterChip({ filter, value, onRemove }: { filter: string; value: string; onRemove: () => void }) {
  const t = useT();
  return (
    <span className="inline-flex h-7 items-center rounded-control border border-line-strong bg-neutral-soft pl-2.5 text-meta font-medium" data-set-filter="">
      {value}
      <button
        type="button"
        aria-label={t('inventory.filters.remove', { filter, value })}
        onClick={onRemove}
        className="inline-flex size-[26px] items-center justify-center rounded-control text-muted hover:text-fg"
      >
        <NavIcon id="close" />
      </button>
    </span>
  );
}

/** The chips of what is set, then "Clear filters"; nothing when nothing is set. */
function SetFilters({ chips, onClear }: { chips: { filter: string; value: string; onRemove: () => void }[]; onClear: () => void }) {
  const t = useT();
  if (chips.length === 0) return null;
  return (
    <>
      {chips.map((chip) => (
        <SetFilterChip key={chip.filter} {...chip} />
      ))}
      <button type="button" onClick={onClear} className="px-1 text-meta text-muted underline underline-offset-[3px] hover:text-fg">
        {t('inventory.filters.clear')}
      </button>
    </>
  );
}

/** The Obligations tab's Filters button, its sheet and the chips of what is set. "As of" keeps its banner rather than a chip. */
export function InventoryFilterBar({ filters, onChange }: { filters: InventoryFilters; onChange: (next: Partial<InventoryFilters>) => void }) {
  const t = useT();
  const regimes = useScopedTerms(REGIME, filters.scope);
  const services = useScopedTerms(SERVICE, filters.scope);
  const dutyTypes = useVocabularyValues(DUTY_TYPE).data ?? [];
  const instrumentName = useInstrumentName(filters.instrument, filters.scope);
  const labelOf = (rows: { key: string; label: string }[], key: string) => rows.find((row) => row.key === key)?.label ?? key;
  const cleared = { instrument: '', regime: '', service: '', dutyType: '' };

  const chips = [
    ...(filters.instrument === '' ? [] : [{ filter: t('inventory.filter.instrument'), value: instrumentName, onRemove: () => onChange({ instrument: '' }) }]),
    ...(filters.regime === '' ? [] : [{ filter: t('inventory.filter.regime'), value: labelOf(regimes.all, filters.regime), onRemove: () => onChange({ regime: '' }) }]),
    ...(filters.service === '' ? [] : [{ filter: t('inventory.filter.service'), value: labelOf(services.all, filters.service), onRemove: () => onChange({ service: '' }) }]),
    ...(filters.dutyType === '' ? [] : [{ filter: t('inventory.filter.dutyType'), value: labelOf(dutyTypes, filters.dutyType), onRemove: () => onChange({ dutyType: '' }) }]),
  ];

  return (
    <>
      <FilterSheet onClear={() => onChange({ ...cleared, asOf: '' })}>
        <InstrumentPicker value={filters.instrument} scope={filters.scope} onChange={(instrument) => onChange({ instrument })} />
        <ToggleGroup label={t('inventory.filter.regime')} values={regimes.offered} value={filters.regime} onChange={(regime) => onChange({ regime })} />
        <ToggleGroup label={t('inventory.filter.service')} values={services.offered} value={filters.service} onChange={(service) => onChange({ service })} />
        <ToggleGroup label={t('inventory.filter.dutyType')} values={dutyTypes} value={filters.dutyType} onChange={(dutyType) => onChange({ dutyType })} />
        <div>
          <label htmlFor="inventory-as-of" className="microlabel mb-2 block text-muted">
            {t('inventory.asOf')}
          </label>
          <TextInput id="inventory-as-of" type="date" className="w-auto" value={filters.asOf} onChange={(event) => onChange({ asOf: event.target.value })} />
        </div>
      </FilterSheet>
      <SetFilters chips={chips} onClear={() => onChange(cleared)} />
    </>
  );
}

/** The Instruments tab's Filters button: Regime, the one filter GET /instruments takes besides the scope. */
export function InstrumentFilterBar({ filters, onChange }: { filters: InstrumentFilters; onChange: (next: Partial<InstrumentFilters>) => void }) {
  const t = useT();
  const regimes = useScopedTerms(REGIME, filters.scope);
  const chips =
    filters.regime === ''
      ? []
      : [{ filter: t('inventory.filter.regime'), value: regimes.all.find((row) => row.key === filters.regime)?.label ?? filters.regime, onRemove: () => onChange({ regime: '' }) }];
  return (
    <>
      <FilterSheet onClear={() => onChange({ regime: '' })}>
        <ToggleGroup label={t('inventory.filter.regime')} values={regimes.offered} value={filters.regime} onChange={(regime) => onChange({ regime })} />
      </FilterSheet>
      <SetFilters chips={chips} onClear={() => onChange({ regime: '' })} />
    </>
  );
}
