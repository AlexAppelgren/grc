'use client';

import { Chip } from '@/components/ui/Chip';
import { Select, TextInput } from '@/components/ui/Field';
import { useTerms } from '@/features/footprint/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// The inventory's filters (design/screens/tenant-inventory.html). Regime and
// Service are taxonomy terms, Duty type is a library vocabulary; every option
// carries the row's key and shows the row's label, so a rename never changes
// what a filter means. The instrument filter comes with the Instruments tab.

export const REGIME = 'regime';
export const SERVICE = 'service_type';
export const DUTY_TYPE = 'duty_type';

/** What the screen filters by, all keys and a plain date; never a label. */
export interface InventoryFilters {
  regime: string;
  service: string;
  dutyType: string;
  /** A plain date, YYYY-MM-DD; empty means today where the tenant is. */
  asOf: string;
  outsideFootprint: boolean;
}

export function InventoryFilterBar({ filters, onChange }: { filters: InventoryFilters; onChange: (next: Partial<InventoryFilters>) => void }) {
  const t = useT();
  const regimes = useTerms(REGIME);
  const services = useTerms(SERVICE);
  const dutyTypes = useVocabularyValues(DUTY_TYPE);

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" data-inventory-filters="">
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
