'use client';

import { Chip } from '@/components/ui/Chip';
import { Select, TextInput } from '@/components/ui/Field';
import { useTerms } from '@/features/footprint/hooks';
import { INSTRUMENT_OPTIONS, useInstruments } from '@/features/library/hooks';
import type { Obligation, ScopeFilter } from '@/features/library/types';
import { usePeople } from '@/features/register/hooks';
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
  scope: ScopeFilter;
}

export const SCOPE_VALUES: readonly ScopeFilter[] = ['in', 'watched', 'all'];

/**
 * The regulatory scope filter (FP-03, FP-04): one value of three, so exactly
 * one chip is pressed and no contradictory pair can be sent. The inventory's
 * two tabs and the instrument card's obligations use it alike.
 */
export function ScopeChips({ value, onChange }: { value: ScopeFilter; onChange: (next: ScopeFilter) => void }) {
  const t = useT();
  const label: Record<ScopeFilter, string> = { in: t('library.scope.in'), watched: t('library.scope.watched'), all: t('library.scope.all') };
  return (
    <div role="group" aria-label={t('library.scope.label')} className="flex flex-wrap items-center gap-2">
      {SCOPE_VALUES.map((scope) => (
        <Chip key={scope} pressed={value === scope} onClick={() => onChange(scope)}>
          {label[scope]}
        </Chip>
      ))}
    </div>
  );
}

/**
 * The instrument picker's own options, each with its obligation count (INV-01, T17),
 * read at the route's maximum page so the picker is not cut at the tab's first 20.
 * An instrument in the URL that is not among them keeps an option of its own, so the
 * picker never reads "All instruments" while the list is filtered by one. One outside
 * our scope is named from the options outside it, read only then; the key shows only
 * while that read loads, or for an instrument past the hundredth or unknown.
 */
function InstrumentSelect({ value, scope, onChange }: { value: string; scope: ScopeFilter; onChange: (next: string) => void }) {
  const t = useT();
  const instruments = useInstruments(scope === 'in' ? {} : { footprint: scope }, INSTRUMENT_OPTIONS);
  const options = instruments.data?.items ?? [];
  const unlisted = value !== '' && !options.some((instrument) => instrument.stableKey === value);
  const outside = useInstruments({ footprint: 'all' }, INSTRUMENT_OPTIONS, unlisted && instruments.isSuccess && scope !== 'all');
  const unlistedName = outside.data?.items.find((instrument) => instrument.stableKey === value)?.shortName ?? value;
  return (
    <Select className="w-auto" aria-label={t('inventory.filter.instrument')} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{t('inventory.filter.allInstruments')}</option>
      {unlisted ? <option value={value}>{unlistedName}</option> : null}
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
      <InstrumentSelect value={filters.instrument} scope={filters.scope} onChange={(instrument) => onChange({ instrument })} />
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
      <ScopeChips value={filters.scope} onChange={(scope) => onChange({ scope })} />
    </div>
  );
}

/** The Instruments tab's own filters: GET /instruments takes only regime, q and footprint (chunk3-rest default). */
export interface InstrumentFilters {
  regime: string;
  scope: ScopeFilter;
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
      <ScopeChips value={filters.scope} onChange={(scope) => onChange({ scope })} />
    </div>
  );
}

// c8-ui-inventory-overlay: the bank's register overlay as filters (REG-01, REG-02). Each
// sends a key, or a member's id for the owner, and never a label; the statuses and the
// teams are the bank's own rows, read live, so a relabel never changes what a view means.

export const COMPLIANCE_STATUS = 'compliance_status';
export const TEAM = 'team';

/** The overlay filters; empty means not filtered. */
export interface OverlayFilters {
  applicability: Obligation['applicability'] | '';
  complianceStatus: string;
  owner: string;
  ownerTeam: string;
}

export const APPLICABILITY_VALUES: readonly Obligation['applicability'][] = ['applies', 'not_applicable', 'under_assessment'];

const APPLICABILITY_LABEL = {
  applies: 'obligationApplicability.applies',
  not_applicable: 'obligationApplicability.notApplicable',
  under_assessment: 'obligationApplicability.underAssessment',
} as const;

/** One option per row, and the key in the URL kept as an option of its own when no row names it. */
function KeySelect({ label, any, value, rows, onChange }: { label: string; any: string; value: string; rows: readonly { key: string; label: string }[]; onChange: (next: string) => void }) {
  return (
    <Select className="w-auto" aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{any}</option>
      {value !== '' && !rows.some((row) => row.key === value) ? <option value={value}>{value}</option> : null}
      {rows.map((row) => (
        <option key={row.key} value={row.key}>
          {row.label}
        </option>
      ))}
    </Select>
  );
}

export function OverlayFilterBar({ filters, onChange }: { filters: OverlayFilters; onChange: (next: Partial<OverlayFilters>) => void }) {
  const t = useT();
  const statuses = useVocabularyValues(COMPLIANCE_STATUS);
  const teams = useVocabularyValues(TEAM);
  const people = usePeople();
  const applicability = APPLICABILITY_VALUES.map((key) => ({ key, label: t(APPLICABILITY_LABEL[key]) }));
  const owners = (people.data ?? []).map((person) => ({ key: person.id, label: person.name }));

  return (
    <>
      <KeySelect
        label={t('inventory.filter.applicability')}
        any={t('inventory.filter.anyApplicability')}
        value={filters.applicability}
        rows={applicability}
        onChange={(next) => onChange({ applicability: APPLICABILITY_VALUES.find((key) => key === next) ?? '' })}
      />
      <KeySelect label={t('inventory.filter.complianceStatus')} any={t('inventory.filter.anyComplianceStatus')} value={filters.complianceStatus} rows={statuses.data ?? []} onChange={(complianceStatus) => onChange({ complianceStatus })} />
      <KeySelect label={t('inventory.filter.owner')} any={t('inventory.filter.anyOwner')} value={filters.owner} rows={owners} onChange={(owner) => onChange({ owner })} />
      <KeySelect label={t('inventory.filter.ownerTeam')} any={t('inventory.filter.anyOwnerTeam')} value={filters.ownerTeam} rows={teams.data ?? []} onChange={(ownerTeam) => onChange({ ownerTeam })} />
    </>
  );
}
