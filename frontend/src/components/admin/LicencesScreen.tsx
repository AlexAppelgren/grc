'use client';

import Link from 'next/link';

import { countryName } from '@/components/admin/EntitiesSection';
import { EntityLicences } from '@/components/admin/LicenceRecords';
import { EmptyState } from '@/components/ui/EmptyState';
import { Fold } from '@/components/ui/fold';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { QueryState } from '@/components/ui/States';
import { useApplicabilityCompanies } from '@/features/applies/hooks';
import { useFormatContext } from '@/features/identity/hooks';
import { useCanEditOrganisation, useOrgUnits } from '@/features/tenant-admin/organisation/hooks';
import { entityTree, presentEntity, presentTerms, registerLines, type RegisterLine } from '@/features/tenant-admin/organisation/organisation-presentation';
import type { OrgUnitRow, RegisterEntry } from '@/features/tenant-admin/organisation/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination, unlocks } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { externalHref } from '@/shared/utils/external-href';
import { formatDate } from '@/shared/utils/format';

// Licences (design/screens/admin-licences.html, TEN-02, TEN-07, TEN-S16): every legal
// entity of the bank, in the Organisation page's order, with what the supervisor's
// register lists for it and what each line brings into scope, the licences and
// certificates the bank recorded itself, the terms outside its own scope, and how many
// obligations its licences offer. Any member reads it; Add and Edit show for
// vocab.manage. The register's words are data, shown as the register writes them.

/** Licence lines shown before the rest fold away. */
const SHOWN_LICENCE_LINES = 5;

const whatApplies = (id: string) => `/applies?company=${encodeURIComponent(id)}`;

export function LicencesScreen() {
  const t = useT();
  const units = useOrgUnits();
  const canEdit = useCanEditOrganisation();
  const companies = useApplicabilityCompanies();
  const permissions = usePermissions() ?? [];
  const canSeeScope = unlocks(findDestination('admin-footprint')?.anyOfPermissions ?? [], permissions);
  // What applies reads GET /applicability/companies, which needs register.read.
  const canSeeApplies = permissions.includes('register.read');

  return (
    <>
      <PageHead title={t('admin.licences.title')} lede={t('admin.licences.lede')} />
      <QueryState query={units} errorTitle={t('admin.licences.errorTitle')}>
        {(rows) => {
          const entities = entityTree(rows)
            .map(({ unit }) => unit)
            .filter((unit) => unit.kind === 'legal_entity');
          return entities.length === 0 ? (
            <EmptyState title={t('admin.licences.emptyTitle')} body={t('admin.licences.emptyBody')} action={{ label: t('admin.licences.emptyAction'), href: '/admin/organisation' }} />
          ) : (
            <div data-licences-page="">
              {entities.map((entity) => (
                <CompanyPanel
                  key={entity.id}
                  entity={entity}
                  canEdit={canEdit}
                  canSeeScope={canSeeScope}
                  canSeeApplies={canSeeApplies}
                  offered={companies.data?.find((company) => company.orgUnit.id === entity.id)?.offered}
                />
              ))}
            </div>
          );
        }}
      </QueryState>
    </>
  );
}

function CompanyPanel({ entity, canEdit, canSeeScope, canSeeApplies, offered }: { entity: OrgUnitRow; canEdit: boolean; canSeeScope: boolean; canSeeApplies: boolean; offered: number | undefined }) {
  const t = useT();
  const ctx = useFormatContext();
  const outside = entity.scopeExclusions ?? [];
  const nothing = entity.registerEntry === null && entity.licences.length === 0;
  const headId = `licences-${entity.id}`;
  return (
    <Panel aria-labelledby={headId} className={entity.active ? undefined : 'opacity-60'} data-company={entity.name}>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <h2 id={headId}>{entity.name}</h2>
        <PillRow pills={presentEntity(entity)} />
        <Meta>
          {entity.orgNumber !== '' ? <span className="font-mono">{entity.orgNumber}</span> : null}
          {entity.countryCode !== '' ? <span>{countryName(entity.countryCode, ctx)}</span> : null}
          {entity.active ? null : <span>{t('admin.org.entities.inactive')}</span>}
        </Meta>
        {/* What applies lists active companies only. */}
        {canSeeApplies && entity.active ? (
          <Link href={whatApplies(entity.id)} aria-label={t('admin.licences.whatAppliesTo', { name: entity.name })} className="ml-auto font-medium whitespace-nowrap underline">
            {t('admin.licences.whatApplies')}
          </Link>
        ) : null}
      </div>
      {entity.registerEntry !== null ? <FromRegister entry={entity.registerEntry} /> : null}
      <EntityLicences entity={entity} canEdit={canEdit} title={nothing ? null : t('admin.licences.recorded')} none={nothing ? t('admin.licences.nothing') : t('admin.licences.none')} />
      {outside.length > 0 ? (
        <section className="mt-4" data-outside-scope="">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
            <h3>{t('admin.org.registers.outside')}</h3>
            {canSeeScope ? (
              <Link href="/admin/footprint" className="ml-auto font-medium whitespace-nowrap underline">
                {t('nav.admin.footprint')}
              </Link>
            ) : null}
          </div>
          <PillRow pills={presentTerms(outside)} />
        </section>
      ) : null}
      {offered !== undefined ? (
        <p className="mt-4 border-t border-line pt-3" data-offered={offered}>
          <Link href={whatApplies(entity.id)} className="font-medium underline">
            {t('admin.licences.offered', { count: offered })}
          </Link>
        </p>
      ) : null}
    </Panel>
  );
}

/** What the register lists for the company, line by line, with the terms each line brings; licence lines past the fifth fold away. */
function FromRegister({ entry }: { entry: RegisterEntry }) {
  const t = useT();
  const ctx = useFormatContext();
  const { businesses, licences } = registerLines(entry);
  const rest = licences.slice(SHOWN_LICENCE_LINES);
  const source = externalHref(entry.sourceUrl);
  return (
    <section className="mt-4" data-register-lines="">
      <h3 className="mb-1">{t('admin.licences.fromRegister')}</h3>
      <Meta className="mb-2">
        <span>{t('admin.licences.readLine', { authority: entry.authority.name, date: formatDate(entry.readAt, ctx) })}</span>
        {source !== null ? (
          <a href={source} target="_blank" rel="noopener noreferrer" className="underline">
            {t('admin.licences.source')}
          </a>
        ) : null}
      </Meta>
      {[...businesses, ...licences.slice(0, SHOWN_LICENCE_LINES)].map((line, i) => (
        <LineRow key={`${i}:${line.text}`} line={line} />
      ))}
      {rest.length > 0 ? (
        <Fold title={t('admin.licences.showMore', { count: rest.length })}>
          {rest.map((line, i) => (
            <LineRow key={`${i}:${line.text}`} line={line} />
          ))}
        </Fold>
      ) : null}
    </section>
  );
}

function LineRow({ line }: { line: RegisterLine }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-t border-line py-2.5" data-register-line="">
      <span className="min-w-0">{line.text}</span>
      {line.grantedOn !== null ? <span className="text-meta whitespace-nowrap text-muted">{t('admin.licences.granted', { date: formatDate(line.grantedOn, ctx) })}</span> : null}
      {line.brings === 'unmapped' ? (
        <p className="basis-full text-meta text-muted" data-unmapped="">
          {t('admin.licences.notUsed')}
        </p>
      ) : line.brings !== null ? (
        <div className="flex basis-full flex-wrap items-center gap-x-2 gap-y-1.5 text-meta text-muted" data-brings="">
          <span>{t('admin.licences.brings')}</span>
          <PillRow pills={line.brings} />
        </div>
      ) : null}
    </div>
  );
}
