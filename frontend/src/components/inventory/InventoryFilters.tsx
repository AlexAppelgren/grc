'use client';

import { Chip } from '@/components/ui/Chip';
import { Select, TextInput } from '@/components/ui/Field';
import { useTerms } from '@/features/footprint/hooks';
import { INSTRUMENT_OPTIONS, useInstruments } from '@/features/library/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// The inventory's filters (design/screens/tenant-inventory.html). Regime and
// Service are taxonomy terms, Duty type is a library vocabulary, Instrument a
// stable key from GET /instruments; every option carries the row's key and
// shows the row's label, so a rename never changes what a filter means.

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
  outsideFootprint: boolean;
}

/**
 * The instrument picker's own options, each with its obligation count (INV-01, T17),
 * read at the route's maximum page so the picker is not cut at the tab's first 20.
 * An instrument in the URL that is not among them (still loading, outside our scope,
 * or past the hundredth) keeps an option of its own, named by its key, so the picker
 * never reads "All instruments" while the list is filtered by one.
 */
function InstrumentSelect({ value, outsideFootprint, onChange }: { value: string; outsideFootprint: boolean; onChange: (next: string) => void }) {
  const t = useT();
  const instruments = useInstruments({ outsideFootprint }, INSTRUMENT_OPTIONS);
  const options = instruments.data?.items ?? [];
  const unlisted = value !== '' && !options.some((instrument) => instrument.stableKey === value);
  return (
    <Select className="w-auto" aria-label={t('inventory.filter.instrument')} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{t('inventory.filter.allInstruments')}</option>
      {unlisted ? <option value={value}>{value}</option> : null}
      {options.map((instrument) => (
        <option key={instrument.stableKey} value={instrument.stableKey}>
          {t('inventory.filter.instrumentOption', { name: instrument.shortName, count: instrument.obligationCount })}
        </option>
      ))}
    </Select>
  );
}

export function InventoryFilterBar({ filters, onChange }: { filters: InventoryFilters; onChange: (next: Partial<InventoryFilters>) => void }) {
  const t = useT();
  const regimes = useTerms(REGIME);
  const services = useTerms(SERVICE);
  const dutyTypes = useVocabularyValues(DUTY_TYPE);

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" data-inventory-filters="">
      <InstrumentSelect value={filters.instrument} outsideFootprint={filters.outsideFootprint} onChange={(instrument) => onChange({ instrument })} />
      <Select className="w-auto" aria-label={t('inventory.filter.regime')} value={filters.regime} onChange={(event) => onChange({ regime: event.target.value })}>
        <option value="">{t('inventory.filter.allRegimes')}</option>
        {(regimes.data ?? []).map((term) => (
          <option key={term.key} value={term.key}>
            {term.label}
          </option>
        ))}
      </Select>
      <Select className="w-auto" aria-label={t('inventory.filter.service')} value={filters.service} onChange={(event) => onChange({ service: event.target.value })}>
        <option value="">{t('inventory.filter.anyService')}</option>
        {(services.data ?? []).map((term) => (
          <option key={term.key} value={term.key}>
            {term.label}
          </option>
        ))}
      </Select>
      <Select className="w-auto" aria-label={t('inventory.filter.dutyType')} value={filters.dutyType} onChange={(event) => onChange({ dutyType: event.target.value })}>
        <option value="">{t('inventory.filter.anyDutyType')}</option>
        {(dutyTypes.data ?? []).map((row) => (
          <option key={row.key} value={row.key}>
            {row.label}
          </option>
        ))}
      </Select>
      <label htmlFor="inventory-as-of" className="text-meta text-muted">
        {t('inventory.asOf')}
      </label>
      <TextInput id="inventory-as-of" type="date" className="w-auto" value={filters.asOf} onChange={(event) => onChange({ asOf: event.target.value })} />
      <Chip pressed={filters.outsideFootprint} onClick={() => onChange({ outsideFootprint: !filters.outsideFootprint })}>
        {t('inventory.showOutside')}
      </Chip>
    </div>
  );
}

/** The Instruments tab's own filters: GET /instruments takes only regime, q and outsideFootprint (chunk3-rest default). */
export interface InstrumentFilters {
  regime: string;
  outsideFootprint: boolean;
}

export function InstrumentFilterBar({ filters, onChange }: { filters: InstrumentFilters; onChange: (next: Partial<InstrumentFilters>) => void }) {
  const t = useT();
  const regimes = useTerms(REGIME);

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" data-instrument-filters="">
      <Select className="w-auto" aria-label={t('inventory.filter.regime')} value={filters.regime} onChange={(event) => onChange({ regime: event.target.value })}>
        <option value="">{t('inventory.filter.allRegimes')}</option>
        {(regimes.data ?? []).map((term) => (
          <option key={term.key} value={term.key}>
            {term.label}
          </option>
        ))}
      </Select>
      <Chip pressed={filters.outsideFootprint} onClick={() => onChange({ outsideFootprint: !filters.outsideFootprint })}>
        {t('inventory.showOutside')}
      </Chip>
    </div>
  );
}
