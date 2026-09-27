'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Meta } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useStatementOfApplicability } from '@/features/register/hooks';
import { presentApplicability, presentCompliance } from '@/features/register/register-presentation';
import type { RegisterPerson } from '@/features/register/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// The Statement of Applicability: the register filtered by a standard and one
// legal entity (design/screens/tenant-obligation-units.html, frame 12; REG-08,
// REG-S15). The conformance row keeps its own assessed status, which no unit
// changes; below it, each unit with its reference, the bank's title, its
// decision, reason and status, who set it and when, and its history of
// decisions. Read-only: units and decisions are edited on the Units tab.

const PAGE_SIZE = 100;
const cell = 'border-b border-line px-2 py-1.5 text-left align-top';

export function SoaView({ obligationId, entity }: { obligationId: string; entity: { id: string; name: string } }) {
  const t = useT();
  const ctx = useFormatContext();
  const [offset, setOffset] = useState(0);
  const statement = useStatementOfApplicability(obligationId, entity.id, { limit: PAGE_SIZE, offset });

  if (statement.isPending) return <LoadingState />;
  if (statement.isError) return <ErrorState title={t('obligationUnits.soaLoadError')} onRetry={() => void statement.refetch()} />;

  const { conformance, units, total } = statement.data;
  const setBy = (person: RegisterPerson | null | undefined) => (person == null ? t('obligationUnits.noneYet') : person.name);
  const decided = (at: string | null | undefined) => (at == null ? t('obligationUnits.noneYet') : formatDate(at, ctx));

  return (
    <div data-soa={entity.id}>
      <p className="mb-3 text-muted">{t('obligationUnits.soaLede', { entity: entity.name })}</p>
      <section className="mb-4 rounded-card border border-line p-4" data-soa-conformance="">
        <h3 className="mb-2">{t('obligationUnits.soaConformance', { entity: entity.name })}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <PillRow pills={[presentApplicability(conformance.applicability, t), presentCompliance(conformance.complianceStatus)]} />
          <Meta>
            {conformance.applicabilityReason == null ? null : <span>{conformance.applicabilityReason}</span>}
            <span>{t('obligationUnits.setBy', { person: setBy(conformance.applicabilityDecidedBy) })}</span>
            <span>{decided(conformance.applicabilityDecidedAt)}</span>
          </Meta>
        </div>
        <p className="mt-2 text-meta text-muted">{t('obligationUnits.soaConformanceNote')}</p>
      </section>

      {total === 0 ? (
        <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-soa-empty="">
          <h3 className="text-fg">{t('obligationUnits.emptyTitle', { entity: entity.name })}</h3>
          <p className="mx-auto mt-2 max-w-[60ch]">{t('obligationUnits.soaEmptyBody')}</p>
        </div>
      ) : (
        <>
          <p className="mb-2 text-meta text-muted">{t('obligationUnits.count', { count: total })}</p>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-meta">
              <thead>
                <tr>
                  <th className={cell}>{t('obligationUnits.columnReference')}</th>
                  <th className={cell}>{t('obligationUnits.columnTitle')}</th>
                  <th className={cell}>{t('obligationUnits.columnApplicability')}</th>
                  <th className={cell}>{t('obligationUnits.columnReason')}</th>
                  <th className={cell}>{t('obligationUnits.columnStatus')}</th>
                  <th className={cell}>{t('obligationUnits.columnSetBy')}</th>
                  <th className={cell}>{t('obligationUnits.columnDecided')}</th>
                  <th className={cell}>{t('obligationUnits.columnHistory')}</th>
                </tr>
              </thead>
              <tbody>
                {units.map((unit) => (
                  <tr key={unit.id} data-soa-unit={unit.reference}>
                    <td className={`${cell} font-mono`}>{unit.reference}</td>
                    <td className={cell}>{unit.title}</td>
                    <td className={cell}>
                      <PillRow pills={[presentApplicability(unit.applicability, t)]} />
                    </td>
                    <td className={cell}>{unit.applicabilityReason ?? t('obligationUnits.noneYet')}</td>
                    <td className={cell}>
                      <PillRow pills={[presentCompliance(unit.complianceStatus)]} />
                    </td>
                    <td className={cell}>{setBy(unit.applicabilityDecidedBy)}</td>
                    <td className={cell}>{decided(unit.applicabilityDecidedAt)}</td>
                    <td className={cell}>
                      {unit.history.length === 0 ? (
                        t('obligationUnits.noneYet')
                      ) : (
                        <details data-soa-history="">
                          <summary className="cursor-pointer">{t('obligationUnits.historyCount', { count: unit.history.length })}</summary>
                          <ol className="mt-1.5 grid gap-1.5">
                            {unit.history.map((decision, index) => (
                              <li key={`${decision.decidedAt}-${index}`}>
                                <PillRow pills={[presentApplicability(decision.applicability, t)]} />
                                <span className="block">{decision.reason}</span>
                                <span className="block text-muted">
                                  {t('obligationUnits.historyEntry', { person: decision.decidedBy.name, date: formatDate(decision.decidedAt, ctx) })}
                                </span>
                              </li>
                            ))}
                          </ol>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {total > PAGE_SIZE ? (
            <ButtonBar>
              <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                {t('obligationUnits.previous')}
              </Button>
              <Button variant="outline" size="small" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                {t('obligationUnits.next')}
              </Button>
            </ButtonBar>
          ) : null}
        </>
      )}
    </div>
  );
}
