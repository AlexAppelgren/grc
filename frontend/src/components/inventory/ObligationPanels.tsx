'use client';

import Link from 'next/link';

import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { useFormatContext } from '@/features/identity/hooks';
import { machineConfirmedLabel, presentScope } from '@/features/library/obligation-presentation';
import type { ObligationDetail, ObligationVersionRow, RelatedObligation } from '@/features/library/types';
import { inForceLabel } from '@/features/library/version-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatDateTime } from '@/shared/utils/format';

// The panels of the obligation card (design/screens/tenant-obligation.html;
// INV-03, INV-05, INV-06). Everything here reads: the library changes only
// through an approved proposal, so no panel writes and none of them says
// whether the duty applies to this bank or whether the bank complies, which
// are the register's facts from chunk 8.

/** Prototype `.kv`: the muted term, the fact beside it. A row with nothing recorded is left out rather than shown empty. */
export interface Fact {
  key: string;
  label: string;
  value: React.ReactNode;
}

export function Facts({ facts }: { facts: readonly Fact[] }) {
  return (
    <dl className="m-0 grid gap-x-3.5 gap-y-2.5 text-meta md:grid-cols-[150px_1fr]">
      {facts.map((fact) => (
        <div key={fact.key} className="contents">
          <dt className="text-muted">{fact.label}</dt>
          <dd className="m-0">{fact.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * "Who and what it covers": one row per scope dimension, then the product
 * scope the library wrote in its own words and the library's tags. The terms
 * are the record's own scope, never this bank's footprint and never a
 * judgement that the duty applies here.
 */
export function ScopePanel({ obligation }: { obligation: ObligationDetail }) {
  const t = useT();
  const facts: Fact[] = obligation.scope.map((dimension) => {
    const presented = presentScope({ dimension: dimension.dimension.key, terms: dimension.terms, allSelected: dimension.allSelected }, t);
    return {
      key: dimension.dimension.key,
      label: dimension.dimension.label,
      value: presented.plainText === undefined ? <PillRow pills={presented.pills} /> : presented.plainText,
    };
  });
  if (obligation.productScope !== '') {
    facts.push({ key: 'product', label: t('inventory.obligation.productLabel'), value: obligation.productScope });
  }
  if (obligation.tags.length > 0) {
    // The library's own keywords, as brand pills like the scope terms they sit
    // beside: the tone comes from the same presentation function, never from here.
    facts.push({
      key: 'tags',
      label: t('inventory.obligation.tagsLabel'),
      value: <PillRow pills={presentScope({ dimension: 'library_tag', terms: obligation.tags, allSelected: false }, t).pills} />,
    });
  }
  return (
    <Panel title={t('inventory.obligation.scopeTitle')} className="bg-subtle" data-scope-panel="">
      <Facts facts={facts} />
    </Panel>
  );
}

/** "The duty": what kind it is and what the source says about when it bites, what is kept and what it costs to miss. */
export function DutyPanel({ obligation }: { obligation: ObligationDetail }) {
  const t = useT();
  const facts: Fact[] = [{ key: 'type', label: t('inventory.obligation.dutyTypeLabel'), value: obligation.dutyType.label }];
  const free: [string, string, string][] = [
    ['trigger', t('inventory.obligation.triggerLabel'), obligation.triggerFrequency],
    ['retention', t('inventory.obligation.retentionLabel'), obligation.retention],
    ['sanction', t('inventory.obligation.sanctionLabel'), obligation.sanctionExposure],
  ];
  for (const [key, label, value] of free) if (value !== '') facts.push({ key, label, value });
  return (
    <Panel title={t('inventory.obligation.dutyTitle')} data-duty-panel="">
      <Facts facts={facts} />
    </Panel>
  );
}

/**
 * Every version with the dates it runs between; nothing here is ever rewritten,
 * so a correction is another row. A version an independent agent confirmed
 * says so where "Approved" would read, always: a person re-verifying the
 * record later does not change who approved that version (D-74).
 */
export function VersionsPanel({ versions }: { versions: readonly ObligationVersionRow[] }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Panel title={t('inventory.obligation.versionsTitle')} data-versions-panel="">
      <div className="text-meta">
        {versions.map((version) => {
          const machine = machineConfirmedLabel(version, null, t, ctx);
          return (
            <div key={version.versionNumber} className="border-b border-line py-2.5 last:border-b-0" data-version-row={version.versionNumber}>
              <time className="block text-muted">{inForceLabel(version.effectiveFrom, version.effectiveTo, t, ctx)}</time>
              {machine !== null ? (
                <span data-machine-confirmed="">{machine}</span>
              ) : version.approvedAt === null ? null : (
                t('inventory.obligation.versionApproved', { date: formatDate(version.approvedAt, ctx) })
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

/** The duties the library files beside this one. A relation is a cross-reference, never a statement that both reach this bank. */
export function RelatedPanel({ related }: { related: readonly RelatedObligation[] }) {
  const t = useT();
  return (
    <Panel title={t('inventory.obligation.relatedTitle')} data-related-panel="">
      {related.length === 0 ? (
        <p className="text-meta text-muted">{t('inventory.obligation.relatedEmpty')}</p>
      ) : (
        <ul className="m-0 grid list-none gap-2.5 p-0">
          {related.map((row) => (
            <li key={row.id}>
              <Link href={`/inventory/obligations/${row.id}`} prefetch={false} className="font-medium underline" data-related-obligation={row.id}>
                {row.title === null ? row.instrument.shortName : row.title.text}
              </Link>
              <Meta className="mt-1">
                <span>{row.instrument.shortName}</span>
                <span>{row.relation.label}</span>
              </Meta>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/**
 * "Where it comes from" (INV-06): the instrument, the public page the record
 * was taken from, when a person last held it against that page, and who
 * drafted it. "by <name>" appears only when somebody has verified it; a
 * seeded record carries a date and no name. When an independent agent
 * confirmed the version on screen and no named person has re-verified the
 * record since, the same slot says so and names the agents instead (INV-05):
 * an older stamp, or one nobody signed, never vouches for wording no person
 * has seen.
 */
export function ProvenancePanel({ obligation, actions }: { obligation: ObligationDetail; actions?: React.ReactNode }) {
  const t = useT();
  const ctx = useFormatContext();
  const { provenance, instrument } = obligation;
  const facts: Fact[] = [
    { key: 'instrument', label: t('inventory.obligation.instrumentLabel'), value: instrument.name === null ? instrument.shortName : instrument.name.text },
    { key: 'ref', label: t('inventory.obligation.officialRefLabel'), value: <span className="font-mono">{instrument.officialRef}</span> },
    { key: 'level', label: t('inventory.obligation.levelLabel'), value: obligation.bindingLevel.label },
  ];
  if (instrument.implementsNote !== '') {
    facts.push({ key: 'implements', label: t('inventory.obligation.implementsLabel'), value: instrument.implementsNote });
  }
  facts.push({
    key: 'source',
    label: t('inventory.obligation.sourceLabel'),
    value: (
      <a href={provenance.sourceUrl} target="_blank" rel="noopener noreferrer" className="underline" data-source-link="">
        {provenance.sourceLabel}
      </a>
    ),
  });
  const machine = machineConfirmedLabel(obligation.version, provenance, t, ctx);
  const verified =
    machine ??
    (provenance.lastVerifiedAt === null
      ? t('library.notVerifiedYet')
      : provenance.verifiedBy === null
        ? formatDate(provenance.lastVerifiedAt, ctx)
        : t('library.lastVerifiedBy', { date: formatDate(provenance.lastVerifiedAt, ctx), name: provenance.verifiedBy.name }));
  facts.push({
    key: 'verified',
    label: t('inventory.obligation.lastVerifiedLabel'),
    value: (
      <span data-last-verified="" data-machine-confirmed={machine === null ? undefined : ''}>
        {verified}
      </span>
    ),
  });
  facts.push({
    key: 'created',
    label: t('inventory.obligation.createdLabel'),
    value:
      provenance.createdOrigin === 'agent' && provenance.createdModel !== ''
        ? t('inventory.obligation.createdByAgent', { date: formatDateTime(provenance.createdAt, ctx), model: provenance.createdModel })
        : t('inventory.obligation.createdByPerson', { date: formatDateTime(provenance.createdAt, ctx) }),
  });
  return (
    <Panel title={t('inventory.obligation.provenanceTitle')} data-provenance-panel="">
      <Facts facts={facts} />
      {actions}
    </Panel>
  );
}

/** What the card will hold and does not yet: the register overlay and the changes filed against this duty. */
export function PendingPanels() {
  const t = useT();
  return (
    <>
      <Panel className="border-dashed" data-pending-panel="changes">
        <h2 className="mb-3 text-muted">{t('inventory.obligation.changesTitle')}</h2>
        <p className="text-meta text-muted">{t('inventory.obligation.changesBody')}</p>
      </Panel>
      <Panel className="border-dashed" data-pending-panel="register">
        <h2 className="mb-3 text-muted">{t('inventory.obligation.registerTitle')}</h2>
        <p className="text-meta text-muted">{t('inventory.obligation.registerBody')}</p>
      </Panel>
    </>
  );
}
