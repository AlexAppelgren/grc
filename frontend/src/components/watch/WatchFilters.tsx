'use client';

import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { Select, TextInput } from '@/components/ui/Field';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useScopeTerms } from '@/features/watch/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// The feed's filters (design/screens/tenant-watch.html). Every option carries
// the row's key, or the term's id where the route matches on one, and shows
// the row's label, so a rename never changes what a filter means.
//
// Two of the card's filters are not here, because the feed read cannot answer
// them: a flag, which `GET /changes` takes no parameter for, and an owner,
// which would need a people reference a watch reader is allowed to call. A
// filter the browser applied to one page of twenty would quietly hide rows,
// so neither is faked here.

export const REGIME = 'regime';
export const CHANGE_TYPE = 'change_type';
export const URGENCY = 'urgency';

/** Which changes to show against the bank's footprint: one value, never a contradictory pair. */
export type ScopeFilter = 'in' | 'watched' | 'all';
export const SCOPE_VALUES: readonly ScopeFilter[] = ['in', 'watched', 'all'];

/** What the screen filters by: keys, one term id and a plain date; never a label. */
export interface WatchFilters {
  regimeTermId: string;
  changeType: string;
  urgency: string;
  week: string;
  unconfirmedSoWhat: boolean;
  scope: ScopeFilter;
}

export const EMPTY_FILTERS: WatchFilters = {
  regimeTermId: '',
  changeType: '',
  urgency: '',
  week: '',
  unconfirmedSoWhat: false,
  scope: 'in',
};

export function WatchFilterBar({
  filters,
  draft,
  onChange,
  onDraft,
  onSearch,
}: {
  filters: WatchFilters;
  /** What is in the search box now. It is the screen's, so clearing the filters clears it too. */
  draft: string;
  onChange: (next: Partial<WatchFilters>) => void;
  onDraft: (phrase: string) => void;
  onSearch: () => void;
}) {
  const t = useT();
  const regimes = useScopeTerms(REGIME);
  const changeTypes = useVocabularyValues(CHANGE_TYPE);
  const urgencies = useVocabularyValues(URGENCY);
  const scopeLabel: Record<ScopeFilter, string> = {
    in: t('watch.filter.inScope'),
    watched: t('watch.filter.watchedMarkets'),
    all: t('watch.filter.showOutside'),
  };

  return (
    <div className="mb-4 grid gap-2" data-watch-filters="">
      <div className="flex flex-wrap items-center gap-2">
        <Select className="w-auto" aria-label={t('watch.filter.regime')} value={filters.regimeTermId} onChange={(event) => onChange({ regimeTermId: event.target.value })}>
          <option value="">{t('watch.filter.allRegimes')}</option>
          {(regimes.data ?? []).map((term) => (
            <option key={term.key} value={term.id}>
              {term.label}
            </option>
          ))}
        </Select>
        <Select className="w-auto" aria-label={t('watch.filter.type')} value={filters.changeType} onChange={(event) => onChange({ changeType: event.target.value })}>
          <option value="">{t('watch.filter.anyType')}</option>
          {(changeTypes.data ?? []).map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </Select>
        <Select className="w-auto" aria-label={t('watch.filter.urgency')} value={filters.urgency} onChange={(event) => onChange({ urgency: event.target.value })}>
          <option value="">{t('watch.filter.anyUrgency')}</option>
          {(urgencies.data ?? []).map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </Select>
        <TextInput type="date" className="w-auto" aria-label={t('watch.filter.week')} value={filters.week} onChange={(event) => onChange({ week: event.target.value })} />
        <form
          role="search"
          className="flex min-w-[20ch] flex-1 items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            onSearch();
          }}
        >
          {/* What someone typed is this bank's own words, so it is sent when
              they ask for it rather than written into the address bar on every
              keystroke (playbook 4.7: a query string is tenant content). */}
          <TextInput type="search" aria-label={t('watch.filter.search')} value={draft} onChange={(event) => onDraft(event.target.value)} />
          <Button type="submit" variant="outline" size="small">
            {t('watch.filter.searchAction')}
          </Button>
        </form>
      </div>
      <div role="group" aria-label={t('watch.filter.scope')} className="flex flex-wrap items-center gap-2">
        {SCOPE_VALUES.map((value) => (
          // Exactly one is pressed: choosing one replaces the others rather
          // than adding to them, so the read is sent one footprint value.
          <Chip key={value} pressed={filters.scope === value} onClick={() => onChange({ scope: value })}>
            {scopeLabel[value]}
          </Chip>
        ))}
        <Chip pressed={filters.unconfirmedSoWhat} onClick={() => onChange({ unconfirmedSoWhat: !filters.unconfirmedSoWhat })}>
          {t('watch.filter.unconfirmedSoWhat')}
        </Chip>
      </div>
    </div>
  );
}
