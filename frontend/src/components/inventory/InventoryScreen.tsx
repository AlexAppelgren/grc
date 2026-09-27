'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import {
  APPLICABILITY_VALUES,
  InstrumentFilterBar,
  InventoryFilterBar,
  OverlayFilterBar,
  REGIME,
  SCOPE_VALUES,
  SERVICE,
  type InstrumentFilters,
  type InventoryFilters,
  type OverlayFilters,
} from '@/components/inventory/InventoryFilters';
import { InstrumentRow } from '@/components/inventory/InstrumentRow';
import { ObligationRow } from '@/components/inventory/ObligationRow';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Pill } from '@/components/ui/Pill';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { TabPanel, Tabs } from '@/components/ui/Tabs';
import { VocabularyPicker } from '@/components/vocabularies/VocabularyPicker';
import { useFormatContext } from '@/features/identity/hooks';
import type { TaggingBatch } from '@/features/library/api';
import { bulkTaggingCap, useInstruments, useObligations, usePreviewObligationTagging, useTagObligations } from '@/features/library/hooks';
import type { InstrumentQuery, Obligation, ObligationQuery, ScopeFilter } from '@/features/library/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { presentVocabularyValue } from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination, unlocks } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';
import { problemFrom } from '@/shared/utils/problem';

// /inventory (design/screens/tenant-inventory.html; INV-01, INV-03, INV-04,
// FP-03, J-6). The filters live in the URL as keys and a plain date, so a
// view is linkable and "as of" is never today by accident. Obligations and
// Instruments are two tabs of the one screen, switched by the `tab` query
// parameter so a link to either is bookmarkable.
//
// The one write is bulk tagging (VOC-08, blocks 1 to 12 of the card): a holder
// of vocab.manage selects rows on the page, picks one of the bank's tags, sees
// the server's preview and commits the ids that preview showed, as one call the
// server audits once. The selection holds while a filter changes, but only rows
// still in view count, and it clears when the page (the tab) changes, so Tag
// never acts on a row the person is no longer looking at.
//
// The bank's register overlay (REG-01, REG-02) filters beside "Our tags":
// whether it applies, how the bank stands, the first-line owner and the owning
// team, each a key (a member's id for the owner) in the URL like the rest.

export type InventoryTab = 'obligations' | 'instruments';

/**
 * The inventory's filters plus the obligations' own: "Our tags", one of the bank's tag
 * keys, and the register overlay's; each empty or absent means not filtered.
 */
export type ScreenFilters = InventoryFilters & { tenantTag?: string } & Partial<OverlayFilters>;

/** The overlay filters in the order the URL carries them. */
const OVERLAY_KEYS = ['applicability', 'complianceStatus', 'owner', 'ownerTeam'] as const;

const TENANT_TAG = 'tenant_tag';
const VOCAB_MANAGE = 'vocab.manage';

/** The URL's tab; anything but "instruments" reads as the default. */
export function tabFrom(params: { get(name: string): string | null }): InventoryTab {
  return params.get('tab') === 'instruments' ? 'instruments' : 'obligations';
}

/** The URL's scope; anything but one of the three values reads as the default, "In our scope". */
function scopeFrom(value: string | null): ScopeFilter {
  return SCOPE_VALUES.find((scope) => scope === value) ?? 'in';
}

/** The URL's filters. Unknown or missing parameters read as "not filtered". */
export function filtersFrom(params: { get(name: string): string | null }): ScreenFilters {
  return {
    instrument: params.get('instrument') ?? '',
    regime: params.get('regime') ?? '',
    service: params.get('service') ?? '',
    dutyType: params.get('dutyType') ?? '',
    asOf: params.get('asOf') ?? '',
    scope: scopeFrom(params.get('scope')),
    tenantTag: params.get('tenantTag') ?? '',
    applicability: APPLICABILITY_VALUES.find((value) => value === params.get('applicability')) ?? '',
    complianceStatus: params.get('complianceStatus') ?? '',
    owner: params.get('owner') ?? '',
    ownerTeam: params.get('ownerTeam') ?? '',
  };
}

/** The filters back into a query string: keys only, and nothing for a filter that is not set. */
export function searchOf(tab: InventoryTab, filters: ScreenFilters): string {
  const search = new URLSearchParams();
  if (tab === 'instruments') search.set('tab', 'instruments');
  if (filters.instrument !== '') search.set('instrument', filters.instrument);
  if (filters.regime !== '') search.set('regime', filters.regime);
  if (filters.service !== '') search.set('service', filters.service);
  if (filters.dutyType !== '') search.set('dutyType', filters.dutyType);
  if (filters.asOf !== '') search.set('asOf', filters.asOf);
  if (filters.scope !== 'in') search.set('scope', filters.scope);
  if (filters.tenantTag !== undefined && filters.tenantTag !== '') search.set('tenantTag', filters.tenantTag);
  for (const key of OVERLAY_KEYS) {
    const value = filters[key];
    if (value !== undefined && value !== '') search.set(key, value);
  }
  return search.toString();
}

/** The obligations read's query: a scope filter is a `dimension:key` term, the way the route reads it. */
export function queryOf(filters: ScreenFilters): ObligationQuery {
  const term = [
    ...(filters.regime === '' ? [] : [`${REGIME}:${filters.regime}`]),
    ...(filters.service === '' ? [] : [`${SERVICE}:${filters.service}`]),
  ];
  const query: ObligationQuery = {};
  if (filters.instrument !== '') query.instrument = filters.instrument;
  if (term.length > 0) query.term = term;
  if (filters.dutyType !== '') query.dutyType = filters.dutyType;
  if (filters.asOf !== '') query.asOf = filters.asOf;
  if (filters.scope !== 'in') query.footprint = filters.scope;
  if (filters.tenantTag !== undefined && filters.tenantTag !== '') query.tenantTag = [filters.tenantTag];
  if (filters.applicability !== undefined && filters.applicability !== '') query.applicability = filters.applicability;
  if (filters.complianceStatus !== undefined && filters.complianceStatus !== '') query.complianceStatus = filters.complianceStatus;
  if (filters.owner !== undefined && filters.owner !== '') query.owner = filters.owner;
  if (filters.ownerTeam !== undefined && filters.ownerTeam !== '') query.ownerTeam = filters.ownerTeam;
  return query;
}

/** The instruments read's query: regime, q and footprint only (chunk3-rest default). */
export function instrumentQueryOf(filters: InstrumentFilters): InstrumentQuery {
  const query: InstrumentQuery = {};
  if (filters.regime !== '') query.regime = filters.regime;
  if (filters.scope !== 'in') query.footprint = filters.scope;
  return query;
}

/** Whether the reader narrowed the list, which decides which empty state answers them. */
export function isNarrowed(filters: ScreenFilters): boolean {
  return (
    filters.instrument !== '' ||
    filters.regime !== '' ||
    filters.service !== '' ||
    filters.dutyType !== '' ||
    filters.asOf !== '' ||
    (filters.tenantTag ?? '') !== '' ||
    OVERLAY_KEYS.some((key) => (filters[key] ?? '') !== '')
  );
}

/** The ids of the selection that are on the page now: the only ones Tag may name. */
export function selectedInView(selected: ReadonlySet<string>, items: readonly Obligation[]): Obligation[] {
  return items.filter((obligation) => selected.has(obligation.id));
}

/** "Our tags": the bank's own tags as a filter every role reads; it sends the key, never the label. */
function TenantTagSelect({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const t = useT();
  const tags = useVocabularyValues(TENANT_TAG);
  const rows = tags.data ?? [];
  if (tags.isSuccess && rows.length === 0 && value === '') {
    return (
      <Select className="w-auto" aria-label={t('inventory.filter.tenantTag')} value="" disabled>
        <option value="">{t('inventory.filter.noTenantTags')}</option>
      </Select>
    );
  }
  return (
    <Select className="w-auto" aria-label={t('inventory.filter.tenantTag')} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{t('inventory.filter.anyTenantTag')}</option>
      {value !== '' && !rows.some((row) => row.key === value) ? <option value={value}>{value}</option> : null}
      {rows.map((row) => (
        <option key={row.key} value={row.key}>
          {row.label}
        </option>
      ))}
    </Select>
  );
}

/** The select-all for the page: checked when every row is, mixed when some are. */
function SelectAll({ count, selectedCount, onChange }: { count: number; selectedCount: number; onChange: (checked: boolean) => void }) {
  const t = useT();
  const box = useRef<HTMLInputElement>(null);
  const mixed = selectedCount > 0 && selectedCount < count;
  useEffect(() => {
    if (box.current !== null) box.current.indeterminate = mixed;
  }, [mixed]);
  return (
    <label className="mb-2.5 ml-4 flex items-center gap-2.5 font-semibold">
      <input ref={box} type="checkbox" className="size-5 accent-button" checked={count > 0 && selectedCount === count} onChange={(event) => onChange(event.target.checked)} data-select-all="" />
      {t('inventory.bulk.selectAll', { count })}
    </label>
  );
}

/** The refusals said in the dialog's own words; anything else offers Try again. */
const KNOWN_REFUSALS: ReadonlySet<string> = new Set(['too_many_records', 'unknown_key', 'permission_denied']);

/**
 * Tag, then Preview, then the commit. The preview and the commit are two calls, and
 * the commit names the ids the preview showed (would gain, already carry), not the
 * selection as it may since have become. Every count is the server's.
 */
function BulkTagDialog({ rows, onClose, onDone }: { rows: readonly Obligation[]; onClose: () => void; onDone: (result: TaggingBatch) => void }) {
  const t = useT();
  const [tagKey, setTagKey] = useState('');
  const values = useVocabularyValues(TENANT_TAG);
  const preview = usePreviewObligationTagging();
  const commit = useTagObligations();
  const shown = preview.data;
  const titles = new Map(rows.map((row) => [row.id, row.title === null ? row.refLabel : row.title.text]));
  const tagLabel = shown?.tag.label ?? values.data?.find((row) => row.key === tagKey)?.label ?? tagKey;
  const failed = commit.isError ? commit : preview.isError ? preview : null;

  let title = t('inventory.bulk.chooseTitle', { count: rows.length });
  if (shown !== undefined) title = shown.gained.count === 0 ? t('inventory.bulk.nothingTitle') : t('inventory.bulk.previewTitle', { tag: shown.tag.label, count: rows.length });

  const back = () => {
    preview.reset();
    commit.reset();
  };
  const run = () => {
    if (tagKey === '') return;
    commit.reset();
    preview.mutate({ tagKey, obligationIds: rows.map((row) => row.id) });
  };
  const send = () => {
    if (shown === undefined) return;
    commit.mutate({ tagKey: shown.tag.key, obligationIds: [...shown.gained.ids, ...shown.alreadyTagged.ids] }, { onSuccess: onDone });
  };
  const tagPill = shown === undefined ? null : presentVocabularyValue(TENANT_TAG, { key: shown.tag.key, kind: shown.tag.kind, label: shown.tag.label, extra: {} });

  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={title}>
      <div data-bulk-tag="" aria-busy={preview.isPending || commit.isPending}>
        {shown === undefined ? (
          <>
            <VocabularyPicker list={TENANT_TAG} tier="tenant" label={t('inventory.bulk.tagField')} value={tagKey === '' ? [] : [tagKey]} onChange={(keys) => setTagKey(keys[keys.length - 1] ?? '')} />
            <p className="mt-1.5 text-meta text-muted">{t('inventory.bulk.chooseHint')}</p>
            {preview.isPending ? <LoadingState rows={1} /> : null}
          </>
        ) : (
          <>
            <dl className="m-0 mb-3.5 grid grid-cols-3 gap-2.5" data-bulk-counts="">
              {[
                ['gained', shown.gained.count, t('inventory.bulk.wouldGain')] as const,
                ['already', shown.alreadyTagged.count, t('inventory.bulk.alreadyCarry')] as const,
                ['skipped', shown.skipped, t('inventory.bulk.skipped')] as const,
              ].map(([key, count, label]) => (
                <div key={key} className="rounded-card border border-line p-3" data-bulk-count={key}>
                  <dd className="m-0 text-title font-semibold">{count}</dd>
                  <dt className="text-meta text-muted">{label}</dt>
                </div>
              ))}
            </dl>
            {shown.gained.count === 0 && shown.skipped === 0 ? (
              <p className="text-meta text-muted">{t('inventory.bulk.allCarry', { count: shown.alreadyTagged.count, tag: shown.tag.label })}</p>
            ) : null}
            <ul className="m-0 grid list-none gap-2 p-0" data-bulk-preview="">
              {shown.gained.ids.map((id) => (
                <li key={id} data-bulk-preview-row="gains" data-obligation-id={id}>
                  <span className="block">{titles.get(id) ?? id}</span>
                  <span className="text-meta text-muted">{t('inventory.bulk.wouldGain')}</span>
                </li>
              ))}
              {shown.alreadyTagged.ids.map((id) => (
                <li key={id} data-bulk-preview-row="carries" data-obligation-id={id}>
                  <span className="block">{titles.get(id) ?? id}</span>
                  <span className="flex items-center gap-1.5 text-meta text-muted">
                    {tagPill === null ? null : (
                      <Pill tone={tagPill.tone} outlined={tagPill.outlined}>
                        {tagPill.label}
                      </Pill>
                    )}
                    {t('inventory.bulk.alreadyCarries')}
                  </span>
                </li>
              ))}
            </ul>
            {shown.skipped > 0 ? <p className="mt-2.5 text-meta text-muted">{t('inventory.bulk.skippedNote', { count: shown.skipped })}</p> : null}
            {shown.gained.count > 0 ? <p className="mt-2.5 text-meta text-muted">{t('inventory.bulk.auditNote')}</p> : null}
          </>
        )}

        {failed === null ? null : KNOWN_REFUSALS.has(problemFrom(failed.error)?.code ?? '') ? (
          <ProblemAlert
            error={failed.error}
            codes={{ too_many_records: t('inventory.bulk.tooMany'), unknown_key: t('inventory.bulk.retired', { tag: tagLabel }), permission_denied: t('inventory.bulk.denied') }}
          />
        ) : (
          <div role="alert" className="mt-2.5 flex flex-wrap items-center gap-2" data-bulk-tag-failed="">
            <span className="text-meta text-negative">{t('inventory.bulk.failed')}</span>
            <Button variant="outline" size="small" onClick={failed === commit ? send : run}>
              {t('common.tryAgain')}
            </Button>
          </div>
        )}

        <ButtonBar className="mt-4">
          {shown === undefined ? (
            <>
              <Button variant="ghost" onClick={onClose}>
                {t('common.cancel')}
              </Button>
              <Button onClick={run} disabled={tagKey === '' || preview.isPending}>
                {t('inventory.bulk.preview')}
              </Button>
            </>
          ) : shown.gained.count === 0 ? (
            <Button onClick={onClose}>{t('inventory.bulk.close')}</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={back} disabled={commit.isPending}>
                {t('common.back')}
              </Button>
              <Button onClick={send} disabled={commit.isPending}>
                {t('inventory.bulk.commit', { count: shown.gained.count })}
              </Button>
            </>
          )}
        </ButtonBar>
      </div>
    </Modal>
  );
}

function ObligationsTab({ filters, apply, pathname }: { filters: ScreenFilters; apply: (patch: Partial<ScreenFilters>) => void; pathname: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const permissions = usePermissions();
  const obligations = useObligations(queryOf(filters));
  const items = obligations.data?.items ?? [];
  const total = obligations.data?.total ?? 0;
  const outsideHref = `${pathname}?${searchOf('obligations', { ...filters, scope: 'all' })}`;
  const untagged = searchOf('obligations', { ...filters, tenantTag: '' });
  const untaggedHref = untagged === '' ? pathname : `${pathname}?${untagged}`;
  const manages = permissions?.includes(VOCAB_MANAGE) === true;
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [tagging, setTagging] = useState(false);
  const [done, setDone] = useState<TaggingBatch | null>(null);
  const inView = selectedInView(selected, items);
  const cap = bulkTaggingCap();
  const overCap = inView.length > cap;

  const toggle = (id: string, checked: boolean) => {
    const next = new Set(selected);
    if (checked) next.add(id);
    else next.delete(id);
    setSelected(next);
  };
  const toggleAll = (checked: boolean) => setSelected(checked ? new Set(items.map((obligation) => obligation.id)) : new Set());
  const openTag = () => {
    // Refused here, before any call, above the cap; the server refuses the same.
    if (overCap || inView.length === 0) return;
    setDone(null);
    setTagging(true);
  };
  // The way to the regulatory scope shows only to someone the scope page opens for.
  const scopePage = findDestination('admin-footprint');
  const scopeAction =
    scopePage !== undefined && unlocks(scopePage.anyOfPermissions, permissions ?? []) ? { label: t('inventory.empty.inScope.action'), href: scopePage.href } : undefined;

  return (
    <>
      <InventoryFilterBar filters={filters} onChange={apply} />
      <div className="-mt-2 mb-4 flex flex-wrap items-center gap-2">
        <TenantTagSelect value={filters.tenantTag ?? ''} onChange={(tenantTag) => apply({ tenantTag })} />
        <OverlayFilterBar
          filters={{ applicability: filters.applicability ?? '', complianceStatus: filters.complianceStatus ?? '', owner: filters.owner ?? '', ownerTeam: filters.ownerTeam ?? '' }}
          onChange={apply}
        />
      </div>

      {filters.asOf === '' ? null : (
        <Notice className="flex flex-wrap items-center gap-2" data-as-of={filters.asOf}>
          <span>{t('inventory.asOfBanner', { date: formatDate(filters.asOf, ctx) })}</span>
          <Button variant="ghost" size="small" onClick={() => apply({ asOf: '' })}>
            {t('inventory.backToToday')}
          </Button>
        </Notice>
      )}

      {done === null ? null : (
        <div className="mb-3" data-bulk-tag-done="">
          <StatusLine tone="positive">
            {done.alreadyTagged.count > 0
              ? `${t('inventory.bulk.done', { tag: done.tag.label, count: done.gained.count })} ${t('inventory.bulk.doneAlready', { count: done.alreadyTagged.count })}`
              : t('inventory.bulk.done', { tag: done.tag.label, count: done.gained.count })}
          </StatusLine>
        </div>
      )}

      {manages && inView.length > 0 ? (
        <div role="region" aria-label={t('inventory.bulk.selection')} className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-card border border-fg bg-surface px-3.5 py-2.5" data-bulk-selection="">
          <b>{t('inventory.bulk.selected', { count: inView.length })}</b>
          <ButtonBar className="mt-0">
            <Button variant="ghost" size="small" onClick={() => setSelected(new Set())}>
              {t('inventory.bulk.clear')}
            </Button>
            <Button size="small" onClick={openTag} disabled={overCap} aria-describedby={overCap ? 'bulk-tag-cap' : undefined}>
              {t('inventory.bulk.tag')}
            </Button>
          </ButtonBar>
          {overCap ? (
            <p id="bulk-tag-cap" className="w-full text-meta text-negative">
              {t('inventory.bulk.overCap', { cap })}
            </p>
          ) : null}
        </div>
      ) : null}

      {obligations.isPending ? (
        <LoadingState rows={3} />
      ) : obligations.isError ? (
        <ErrorState title={t('inventory.errorTitle')} onRetry={() => void obligations.refetch()} />
      ) : items.length === 0 ? (
        filters.scope === 'watched' ? (
          <EmptyState title={t('library.empty.watched.title')} body={t('library.empty.watched.body')} />
        ) : (filters.tenantTag ?? '') !== '' ? (
          <EmptyState title={t('inventory.empty.noTagMatch.title')} body={t('inventory.empty.noTagMatch.body')} action={{ label: t('inventory.empty.noTagMatch.action'), href: untaggedHref }} />
        ) : isNarrowed(filters) ? (
          <EmptyState
            title={t('inventory.empty.noMatch.title')}
            body={t('inventory.empty.noMatch.body')}
            action={filters.scope === 'all' ? undefined : { label: t('inventory.showOutside'), href: outsideHref }}
          />
        ) : (
          <EmptyState title={t('inventory.empty.inScope.title')} body={t('inventory.empty.inScope.body')} action={scopeAction} />
        )
      ) : (
        <>
          {manages ? <SelectAll count={items.length} selectedCount={inView.length} onChange={toggleAll} /> : null}
          <div className="grid gap-2" data-obligation-rows="">
            {items.map((obligation) => (
              <ObligationRow
                key={obligation.id}
                obligation={obligation}
                watched={filters.scope === 'watched'}
                selection={manages ? { checked: selected.has(obligation.id), onChange: (checked) => toggle(obligation.id, checked) } : undefined}
              />
            ))}
          </div>
        </>
      )}

      {tagging ? (
        <BulkTagDialog
          rows={inView}
          onClose={() => setTagging(false)}
          onDone={(result) => {
            setTagging(false);
            setSelected(new Set());
            setDone(result);
          }}
        />
      ) : null}

      {items.length < total ? <p className="mt-3 text-meta text-muted">{t('inventory.showingFirst', { shown: items.length, total })}</p> : null}
    </>
  );
}

function InstrumentsTab({ filters, apply, pathname }: { filters: ScreenFilters; apply: (patch: Partial<ScreenFilters>) => void; pathname: string }) {
  const t = useT();
  const instruments = useInstruments(instrumentQueryOf(filters));
  const items = instruments.data?.items ?? [];
  const narrowed = filters.regime !== '';
  const outsideHref = `${pathname}?${searchOf('instruments', { ...filters, scope: 'all' })}`;

  return (
    <>
      <InstrumentFilterBar filters={filters} onChange={apply} />

      {instruments.isPending ? (
        <LoadingState rows={3} />
      ) : instruments.isError ? (
        <ErrorState title={t('inventory.errorTitle')} onRetry={() => void instruments.refetch()} />
      ) : items.length === 0 ? (
        filters.scope === 'watched' ? (
          <EmptyState title={t('library.empty.watched.title')} body={t('library.empty.watchedInstruments.body')} />
        ) : (
          <EmptyState
            title={t('inventory.empty.noInstrumentMatch.title')}
            body={t('inventory.empty.noInstrumentMatch.body')}
            action={narrowed || filters.scope === 'all' ? undefined : { label: t('inventory.showOutside'), href: outsideHref }}
          />
        )
      ) : (
        <div className="grid gap-2" data-instrument-rows="">
          {items.map((instrument) => (
            <InstrumentRow key={instrument.id} instrument={instrument} />
          ))}
        </div>
      )}
    </>
  );
}

export function InventoryScreen() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = tabFrom(params);
  const filters = filtersFrom(params);
  const obligationCount = useObligations(queryOf(filters));
  // The instruments' count is the instruments tab's lede and nothing else, so the
  // obligations tab never asks for it beside its own rows (NFR-02).
  const instrumentCount = useInstruments(instrumentQueryOf(filters), undefined, tab === 'instruments');

  const apply = (patch: Partial<ScreenFilters>) => {
    const search = searchOf(tab, { ...filters, ...patch });
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };
  const selectTab = (next: string) => {
    const search = searchOf(next === 'instruments' ? 'instruments' : 'obligations', filters);
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };

  let lede: string | undefined;
  if (tab === 'instruments') {
    if (instrumentCount.data !== undefined) lede = t('inventory.instrumentCount', { count: instrumentCount.data.total });
  } else if (obligationCount.data !== undefined) {
    lede = t('inventory.count', { count: obligationCount.data.total });
  }

  return (
    <>
      <PageHead
        title={t('inventory.title')}
        lede={lede}
        actions={
          <Link href="/inventory/updates" className="font-medium underline" data-library-updates-link="">
            {t('inventory.libraryUpdatesLink')}
          </Link>
        }
      />
      <Tabs
        tabs={[
          { id: 'obligations', label: t('inventory.tabs.obligations') },
          { id: 'instruments', label: t('inventory.tabs.instruments') },
        ]}
        current={tab}
        onSelect={selectTab}
      />
      {tab === 'obligations' ? (
        <TabPanel id="obligations">
          <ObligationsTab filters={filters} apply={apply} pathname={pathname} />
        </TabPanel>
      ) : (
        <TabPanel id="instruments">
          <InstrumentsTab filters={filters} apply={apply} pathname={pathname} />
        </TabPanel>
      )}
    </>
  );
}
