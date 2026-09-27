'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { CALLS_PAGE } from '@/features/agent-access/api';
import { useAccessCalls } from '@/features/agent-access/hooks';
import { scopeTermCount, toolName } from '@/features/agent-access/presentation';
import type { AccessCall } from '@/features/agent-access/types';
import { useFormatContext } from '@/features/identity/hooks';
import type { MessageKey, Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// The access log of one entry (design/screens/admin-agent-access.html, states
// 6 and 15; ACC-08), newest first, one page at a time. It names what was
// called, never what was asked or answered: the filter names and their key
// values, the record count, the scope and the time taken. Below 768 px each
// row stacks as label and value.

const COLUMNS = [
  'agentAccess.log.when',
  'agentAccess.log.credential',
  'agentAccess.log.person',
  'agentAccess.log.tool',
  'agentAccess.log.filters',
  'agentAccess.log.records',
  'agentAccess.log.scope',
  'agentAccess.log.took',
  'agentAccess.log.status',
] as const satisfies readonly MessageKey[];

/** One call's values, in the order of COLUMNS. */
export function callValues(call: AccessCall, t: Translate, when: string): string[] {
  const filters = Object.keys(call.filters);
  return [
    when,
    `cw_${call.credential.keyPrefix}…`,
    call.person?.name ?? '—',
    toolName(call.tool),
    filters.length === 0 ? t('agentAccess.log.none') : filters.map(toolName).join(', '),
    call.recordCount === null || call.recordCount === undefined ? t('agentAccess.log.recordsUnknown') : String(call.recordCount),
    call.scope.narrowed ? t('agentAccess.log.narrowed', { count: scopeTermCount(call.scope.terms) }) : t('agentAccess.log.whole'),
    t('agentAccess.log.ms', { ms: call.durationMs }),
    String(call.status),
  ];
}

function CallRow({ call }: { call: AccessCall }) {
  const t = useT();
  const ctx = useFormatContext();
  const values = callValues(call, t, formatDateTime(call.at, ctx));
  return (
    <tr data-call-id={call.id} className="border-t border-line max-md:grid max-md:gap-1 max-md:py-2">
      {COLUMNS.map((column, i) => (
        <td key={column} className="py-1.5 pr-3 align-top max-md:flex max-md:gap-2 max-md:py-0">
          <span className="text-muted md:hidden">{t(column)}</span>
          <span>{values[i]}</span>
        </td>
      ))}
    </tr>
  );
}

export function AccessLog({ entryId }: { entryId: string }) {
  const t = useT();
  const [offset, setOffset] = useState(0);
  const calls = useAccessCalls(entryId, offset);

  return (
    <Panel title={t('agentAccess.log.title')} data-access-log="">
      <p className="mb-3 text-muted">{t('agentAccess.log.lede')}</p>
      {calls.isPending ? (
        <LoadingState />
      ) : calls.isError ? (
        <ErrorState title={t('agentAccess.log.errorTitle')} onRetry={() => void calls.refetch()} />
      ) : calls.data.total === 0 ? (
        <EmptyState title={t('agentAccess.log.emptyTitle')} body={t('agentAccess.log.emptyBody')} />
      ) : (
        <>
          <table className="w-full text-meta max-md:block">
            <thead className="text-left text-muted max-md:hidden">
              <tr>
                {COLUMNS.map((column) => (
                  <th key={column} scope="col" className="py-1.5 pr-3 font-medium">
                    {t(column)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="max-md:grid max-md:gap-3">
              {calls.data.items.map((call) => (
                <CallRow key={call.id} call={call} />
              ))}
            </tbody>
          </table>
          <ButtonBar className="items-center">
            <span className="mr-auto text-meta text-muted">{t('agentAccess.log.range', { from: offset + 1, to: offset + calls.data.items.length, total: calls.data.total })}</span>
            <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - CALLS_PAGE))}>
              {t('agentAccess.log.newer')}
            </Button>
            <Button variant="outline" size="small" disabled={offset + CALLS_PAGE >= calls.data.total} onClick={() => setOffset(offset + CALLS_PAGE)}>
              {t('agentAccess.log.older')}
            </Button>
          </ButtonBar>
        </>
      )}
    </Panel>
  );
}
