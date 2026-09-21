'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Fragment, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select, TextInput } from '@/components/ui/Field';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { languageName } from '@/features/library/version-presentation';
import type { SearchHit, SearchHitType, SearchRequestBody } from '@/features/search/types';
import { useSearchResults } from '@/features/search/hooks';
import { highlightSnippet, presentSearchHitRow, validityMeta, versionMeta } from '@/features/search/search-presentation';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import type { Translate } from '@/shared/i18n';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// /search (design/screens/tenant-search.html; SRC-01, SRC-02, FP-03). Hybrid
// search over the shared library: an identifier is won by keyword, a
// concept by meaning, and every hit says which. Nothing here writes.
//
// The typed query is the bank's own words, so — exactly as the watch feed's
// free-text filter — it never reaches the address bar; it lives in
// component state alone and is sent only when the reader asks. Every other
// filter is a key from a vocabulary or a fixed kind, so it is safe in the
// URL and makes the view linkable.
//
// The card also draws an "Instrument" filter. It is cut here: the contract
// has no route that lists instruments to choose from (only
// `GET /obligations` embeds one inside a page of results), and a select with
// no real options would be dead UI rather than a filter (CLAUDE.md
// simplicity: "no screen calls a stub"). Likewise the card's per-hit
// language tag and the "N obligations" instrument summary are not in
// `SearchHit` and are left off rather than invented.

const HIT_TYPES: readonly SearchHitType[] = ['obligation', 'provision', 'change'];
const BINDING_VALUES = ['', 'true', 'false'] as const;
type BindingFilter = (typeof BINDING_VALUES)[number];
// Seeded on day one (SearchRequest.lang); a sixth language arrives by
// seeding a row, not by changing this screen (I18N-01).
const LANGUAGES = ['en', 'sv', 'da', 'nb', 'fi'] as const;

export interface SearchFiltersState {
  type: '' | SearchHitType;
  jurisdiction: string;
  dutyType: string;
  binding: BindingFilter;
  lang: string;
  asOf: string;
  outsideScope: boolean;
}

export const EMPTY_SEARCH_FILTERS: SearchFiltersState = {
  type: '',
  jurisdiction: '',
  dutyType: '',
  binding: '',
  lang: '',
  asOf: '',
  outsideScope: false,
};

function isHitType(value: string | null): value is SearchHitType {
  return value !== null && (HIT_TYPES as readonly string[]).includes(value);
}

function isBinding(value: string | null): value is BindingFilter {
  return value !== null && (BINDING_VALUES as readonly string[]).includes(value);
}

/** The URL's filters. An unknown or missing parameter reads as "not filtered". */
export function filtersFrom(params: { get(name: string): string | null }): SearchFiltersState {
  const type = params.get('type');
  const binding = params.get('binding');
  return {
    type: isHitType(type) ? type : '',
    jurisdiction: params.get('jurisdiction') ?? '',
    dutyType: params.get('dutyType') ?? '',
    binding: isBinding(binding) ? binding : '',
    lang: params.get('lang') ?? '',
    asOf: params.get('asOf') ?? '',
    outsideScope: params.get('outside') === 'true',
  };
}

/** The filters back into a query string; nothing for a filter that is not set. The typed
 * query is deliberately absent (playbook 4.7). */
export function searchOf(filters: SearchFiltersState): string {
  const search = new URLSearchParams();
  if (filters.type !== '') search.set('type', filters.type);
  if (filters.jurisdiction !== '') search.set('jurisdiction', filters.jurisdiction);
  if (filters.dutyType !== '') search.set('dutyType', filters.dutyType);
  if (filters.binding !== '') search.set('binding', filters.binding);
  if (filters.lang !== '') search.set('lang', filters.lang);
  if (filters.asOf !== '') search.set('asOf', filters.asOf);
  if (filters.outsideScope) search.set('outside', 'true');
  return search.toString();
}

/** The request `POST /search` takes: filters compare keys, never labels (SRC-02). */
export function requestOf(filters: SearchFiltersState, q: string): SearchRequestBody {
  const body: SearchRequestBody = { q, limit: 20 };
  if (filters.asOf !== '') body.asOf = filters.asOf;
  if (filters.lang !== '') body.lang = filters.lang;
  if (filters.type !== '') body.types = [filters.type];
  const narrowed = filters.jurisdiction !== '' || filters.dutyType !== '' || filters.binding !== '' || filters.outsideScope;
  if (narrowed) {
    body.filters = {
      ...(filters.jurisdiction === '' ? {} : { jurisdiction: filters.jurisdiction }),
      ...(filters.dutyType === '' ? {} : { dutyType: filters.dutyType }),
      ...(filters.binding === '' ? {} : { binding: filters.binding === 'true' }),
      ...(filters.outsideScope ? { inFootprint: false } : {}),
    };
  }
  return body;
}

export function SearchScreen() {
  const t = useT();
  const locale = useLocale();
  const ctx = useFormatContext();
  const router = useRouter();
  const pathname = usePathname();
  const filters = filtersFrom(useSearchParams());
  // The phrase in the box, and the phrase the last search actually ran with.
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');

  const jurisdictions = useVocabularyValues('jurisdiction');
  const dutyTypes = useVocabularyValues('duty_type');

  const body = query === '' ? null : requestOf(filters, query);
  const results = useSearchResults(body);

  const hrefFor = (next: SearchFiltersState): string => {
    const qs = searchOf(next);
    return qs === '' ? pathname : `${pathname}?${qs}`;
  };
  const apply = (patch: Partial<SearchFiltersState>) => router.replace(hrefFor({ ...filters, ...patch }));
  const run = (phrase: string) => {
    setDraft(phrase);
    setQuery(phrase);
  };

  const items = results.data?.items ?? [];
  const forbidden = forbiddenFrom(results.error);

  return (
    <>
      <PageHead title={t('search.title')} lede={t('search.lede')} />

      <form
        role="search"
        className="mb-3 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          run(draft);
        }}
      >
        <TextInput
          type="search"
          className="flex-1"
          aria-label={t('search.searchLabel')}
          placeholder={t('search.placeholder')}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button type="submit">{t('search.searchAction')}</Button>
      </form>

      <div className="mb-4 flex flex-wrap items-center gap-2" data-search-filters="">
        <Select aria-label={t('search.filter.type')} value={filters.type} onChange={(event) => apply({ type: isHitType(event.target.value) ? event.target.value : '' })}>
          <option value="">{t('search.filter.anyType')}</option>
          <option value="obligation">{t('search.filter.type.obligation')}</option>
          <option value="provision">{t('search.filter.type.provision')}</option>
          <option value="change">{t('search.filter.type.change')}</option>
        </Select>
        <Select aria-label={t('search.filter.jurisdiction')} value={filters.jurisdiction} onChange={(event) => apply({ jurisdiction: event.target.value })}>
          <option value="">{t('search.filter.anyJurisdiction')}</option>
          {(jurisdictions.data ?? []).map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </Select>
        <Select aria-label={t('search.filter.dutyType')} value={filters.dutyType} onChange={(event) => apply({ dutyType: event.target.value })}>
          <option value="">{t('search.filter.anyDutyType')}</option>
          {(dutyTypes.data ?? []).map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </Select>
        <Select aria-label={t('search.filter.binding')} value={filters.binding} onChange={(event) => apply({ binding: isBinding(event.target.value) ? event.target.value : '' })}>
          <option value="">{t('search.filter.anyBinding')}</option>
          <option value="true">{t('search.filter.bindingOnly')}</option>
          <option value="false">{t('search.filter.guidanceOnly')}</option>
        </Select>
        <Select aria-label={t('search.filter.language')} value={filters.lang} onChange={(event) => apply({ lang: event.target.value })}>
          <option value="">{t('search.filter.anyLanguage')}</option>
          {LANGUAGES.map((code) => (
            <option key={code} value={code}>
              {languageName(code, locale)}
            </option>
          ))}
        </Select>
        <span className="ml-auto flex items-center gap-2 text-meta text-muted">
          <span aria-hidden="true">{t('search.filter.asOf')}</span>
          <TextInput type="date" className="w-auto" aria-label={t('search.filter.asOf')} value={filters.asOf} onChange={(event) => apply({ asOf: event.target.value })} />
        </span>
        <Chip pressed={filters.outsideScope} onClick={() => apply({ outsideScope: !filters.outsideScope })}>
          {t('search.filter.outsideScope')}
        </Chip>
      </div>

      {filters.asOf !== '' ? (
        <Notice className="flex flex-wrap items-center gap-2">
          <span>{t('search.asOfBanner', { date: formatDate(filters.asOf, ctx) })}</span>
          <Link href={hrefFor({ ...filters, asOf: '' })} className="font-medium underline">
            {t('search.asOfBanner.back')}
          </Link>
        </Notice>
      ) : null}

      {query === '' ? (
        <SearchStart onPick={run} t={t} />
      ) : results.isPending ? (
        <LoadingState rows={3} />
      ) : forbidden !== null ? (
        <RestrictedScreen {...forbidden} />
      ) : results.isError ? (
        <ErrorState title={t('search.errorTitle')} onRetry={() => void results.refetch()} />
      ) : items.length === 0 ? (
        <SearchNoMatch filters={filters} hrefFor={hrefFor} t={t} />
      ) : (
        <>
          <p className="mb-2.5 text-meta text-muted" role="status">
            {t('search.count', { count: items.length })}
          </p>
          <div className="grid gap-2.5" data-search-rows="">
            {items.map((hit) => (
              <SearchHitRow key={hit.id} hit={hit} query={query} t={t} ctx={ctx} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

function SearchStart({ onPick, t }: { onPick: (phrase: string) => void; t: Translate }) {
  const examples = [
    t('search.example.researchPayments'),
    t('search.example.nudging'),
    t('search.example.flyttratt'),
    t('search.example.cloudVendors'),
  ];
  return (
    <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-search-start="">
      <h2 className="text-fg">{t('search.empty.title')}</h2>
      <p className="mx-auto mt-2 max-w-[60ch]">{t('search.empty.body')}</p>
      <div className="mt-3 flex flex-wrap justify-center gap-2">
        {examples.map((example) => (
          <Chip key={example} pressed={false} onClick={() => onPick(example)}>
            {example}
          </Chip>
        ))}
      </div>
    </div>
  );
}

function SearchNoMatch({ filters, hrefFor, t }: { filters: SearchFiltersState; hrefFor: (next: SearchFiltersState) => string; t: Translate }) {
  if (filters.outsideScope) {
    return <EmptyState title={t('search.empty.noMatch.title')} body={t('search.empty.noMatch.outsideBody')} />;
  }
  return (
    <EmptyState
      title={t('search.empty.noMatch.title')}
      body={t('search.empty.noMatch.body')}
      action={{ label: t('search.empty.noMatch.action'), href: hrefFor({ ...filters, outsideScope: true }) }}
    />
  );
}

const ROW_CLASS = 'block rounded-card border border-line bg-surface px-4 py-3.5 hover:border-fg';

function SearchHitRow({ hit, query, t, ctx }: { hit: SearchHit; query: string; t: Translate; ctx: FormatContext }) {
  const pills = presentSearchHitRow(hit, t);
  const segments = highlightSnippet(hit.snippet, query);
  const meta = [versionMeta(hit, t), validityMeta(hit, t, ctx)].filter((line): line is string => line !== null);

  const content = (
    <>
      <PillRow pills={pills} />
      <h3 className="my-1.5 font-semibold">{hit.title}</h3>
      <p className="text-meta text-muted">
        {segments.map((segment, index) =>
          segment.matched ? (
            <mark key={index} className="rounded-[3px] bg-neutral-soft px-0.5 text-fg">
              {segment.text}
            </mark>
          ) : (
            <Fragment key={index}>{segment.text}</Fragment>
          ),
        )}
      </p>
      {meta.length > 0 ? (
        <p className="mt-1 flex flex-wrap gap-x-2.5 text-meta text-muted">
          {meta.map((line, index) => (
            <span key={index}>{line}</span>
          ))}
        </p>
      ) : null}
    </>
  );

  if (hit.type === 'obligation') {
    return (
      <Link href={`/inventory/obligations/${hit.id}`} prefetch={false} data-hit-type="obligation" className={ROW_CLASS}>
        {content}
      </Link>
    );
  }
  if (hit.type === 'change') {
    return (
      <Link href={`/watch/${hit.id}`} prefetch={false} data-hit-type="change" className={ROW_CLASS}>
        {content}
      </Link>
    );
  }
  // A provision has no screen of its own yet (INV-03..06 open the
  // obligation, never a provision directly), so it renders as a fact rather
  // than a broken or misleading link.
  return (
    <div data-hit-type="provision" className="rounded-card border border-line bg-surface px-4 py-3.5">
      {content}
    </div>
  );
}
