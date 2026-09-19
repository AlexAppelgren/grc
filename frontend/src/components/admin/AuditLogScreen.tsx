'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Select, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { actionLabel, AUDIT_SUBJECT_TYPES, dayRange, diffRows, presentAuditEvent, subjectTypeLabel } from '@/features/governance/audit-presentation';
import { AUDIT_LOG_PAGE, useAuditEvents } from '@/features/governance/hooks';
import type { AuditEvent } from '@/features/governance/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// The tenant audit log (AUD-01; prototype `vAudit()` and the shared states are
// the cut, no card is drawn yet). Written in ink: rows are added, never
// changed, so nothing here can be edited. The four filters are the route's:
// the record kind, one record, one actor and a range of days. A record and an
// actor are picked from a row, because that is where a person meets them; the
// chip above the list says which one is holding.

interface Picked {
  id: string;
  label: string;
}

export function AuditLogScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const [subjectType, setSubjectType] = useState('');
  const [record, setRecord] = useState<Picked | null>(null);
  const [actor, setActor] = useState<Picked | null>(null);
  const [fromDay, setFromDay] = useState('');
  const [toDay, setToDay] = useState('');
  const [offset, setOffset] = useState(0);

  // A changed filter starts again at the first page: the offset of the old
  // result means nothing in the new one.
  function on<T>(set: (value: T) => void): (value: T) => void {
    return (value) => {
      set(value);
      setOffset(0);
    };
  }

  const filtered = subjectType !== '' || record !== null || actor !== null || fromDay !== '' || toDay !== '';
  const log = useAuditEvents({
    subjectType: subjectType === '' ? undefined : subjectType,
    subjectId: record?.id,
    actorId: actor?.id,
    ...dayRange(fromDay, toDay, ctx.timeZone),
    offset,
    limit: AUDIT_LOG_PAGE,
  });

  function clear(): void {
    setSubjectType('');
    setRecord(null);
    setActor(null);
    setFromDay('');
    setToDay('');
    setOffset(0);
  }

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.auditLog.title')} lede={t('admin.auditLog.lede')} />

      <Panel className="grid gap-x-4 md:grid-cols-3" data-audit-filters="">
        <Field id="audit-subject-type" label={t('admin.auditLog.filter.subjectType')}>
          <Select id="audit-subject-type" value={subjectType} onChange={(e) => on(setSubjectType)(e.target.value)}>
            <option value="">{t('admin.auditLog.filter.anyKind')}</option>
            {AUDIT_SUBJECT_TYPES.map((kind) => (
              <option key={kind} value={kind}>
                {subjectTypeLabel(kind)}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="audit-from" label={t('admin.auditLog.filter.from')}>
          <TextInput id="audit-from" type="date" value={fromDay} onChange={(e) => on(setFromDay)(e.target.value)} />
        </Field>
        <Field id="audit-to" label={t('admin.auditLog.filter.to')}>
          <TextInput id="audit-to" type="date" value={toDay} onChange={(e) => on(setToDay)(e.target.value)} />
        </Field>
        <Meta className="md:col-span-3">
          {record !== null ? (
            <Button variant="outline" size="small" onClick={() => on(setRecord)(null)} data-clear-record="">
              {t('admin.auditLog.filter.record', { record: record.label })}
            </Button>
          ) : null}
          {actor !== null ? (
            <Button variant="outline" size="small" onClick={() => on(setActor)(null)} data-clear-actor="">
              {t('admin.auditLog.filter.actor', { actor: actor.label })}
            </Button>
          ) : null}
          {filtered ? (
            <Button variant="ghost" size="small" onClick={clear}>
              {t('admin.auditLog.filter.clear')}
            </Button>
          ) : null}
        </Meta>
      </Panel>

      {log.isPending ? (
        <LoadingState />
      ) : log.isError ? (
        <ErrorState title={t('admin.auditLog.errorTitle')} onRetry={() => void log.refetch()} />
      ) : log.data.items.length === 0 ? (
        <EmptyState title={t('admin.auditLog.emptyTitle')} body={filtered ? t('admin.auditLog.emptyFiltered') : t('admin.auditLog.emptyBody')} />
      ) : (
        <>
          <Panel className="px-4 py-1" data-audit-log="">
            {log.data.items.map((event) => (
              <AuditRow key={event.id} event={event} onRecord={on(setRecord)} onActor={on(setActor)} />
            ))}
          </Panel>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-meta text-muted">
            <span>{t('admin.auditLog.range', { from: offset + 1, to: Math.min(offset + log.data.items.length, log.data.total), total: log.data.total })}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - AUDIT_LOG_PAGE))}>
                {t('admin.auditLog.newer')}
              </Button>
              <Button variant="outline" size="small" disabled={offset + AUDIT_LOG_PAGE >= log.data.total} onClick={() => setOffset(offset + AUDIT_LOG_PAGE)}>
                {t('admin.auditLog.older')}
              </Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function AuditRow({ event, onRecord, onActor }: { event: AuditEvent; onRecord: (picked: Picked) => void; onActor: (picked: Picked) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const changes = diffRows(event.before, event.after);
  const { actor, subjectId } = event;
  const actorId = actor.id;
  return (
    <div
      className="grid gap-1 border-b border-line py-3 last:border-b-0 md:grid-cols-[170px_1fr] md:gap-x-4"
      data-audit-row=""
      data-event-id={event.id}
      data-action={event.action}
      data-subject-type={event.subjectType}
      data-subject-id={event.subjectId ?? undefined}
    >
      <time dateTime={event.createdAt} className="block text-meta text-muted">
        {formatDateTime(event.createdAt, ctx)}
      </time>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <PillRow pills={presentAuditEvent(event, t)} />
          <span className="font-medium">{event.subjectTitle}</span>
        </div>
        <p className="mt-1">{event.summary}</p>
        <Meta className="mt-1">
          <span>{t('admin.auditLog.by', { name: actor.label })}</span>
          <span>{actionLabel(event.action)}</span>
          {subjectId !== null ? (
            <Button variant="ghost" size="small" onClick={() => onRecord({ id: subjectId, label: event.subjectTitle })} data-only-record="">
              {t('admin.auditLog.onlyRecord')}
            </Button>
          ) : null}
          {actorId !== null ? (
            <Button variant="ghost" size="small" onClick={() => onActor({ id: actorId, label: actor.label })} data-only-actor="">
              {t('admin.auditLog.onlyActor')}
            </Button>
          ) : null}
        </Meta>
        {changes.length > 0 ? (
          <table className="mt-2 w-full border-separate border-spacing-0 text-meta" data-audit-diff="">
            <thead className="text-muted">
              <tr>
                <th scope="col" className="w-1/4 border-b border-line py-1 pr-3 text-left font-medium">
                  {t('admin.auditLog.field')}
                </th>
                <th scope="col" className="border-b border-line py-1 pr-3 text-left font-medium">
                  {t('admin.auditLog.before')}
                </th>
                <th scope="col" className="border-b border-line py-1 text-left font-medium">
                  {t('admin.auditLog.after')}
                </th>
              </tr>
            </thead>
            <tbody>
              {changes.map((change) => (
                <tr key={change.field} data-field={change.field}>
                  <th scope="row" className="py-1 pr-3 text-left align-top font-normal text-muted">
                    <code className="font-mono">{change.field}</code>
                  </th>
                  <td className="py-1 pr-3 align-top break-words text-muted" data-before="">
                    {change.before ?? t('admin.auditLog.absent')}
                  </td>
                  <td className="py-1 align-top break-words" data-after="">
                    {change.after ?? t('admin.auditLog.absent')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  );
}
