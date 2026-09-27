'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextInput } from '@/components/ui/Field';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { DialogForm, PersonSelect } from '@/features/tenant-admin/organisation/fields';
import { useCanEditOrganisation, useCreateOrgUnit, useOrgUnits, useUpdateOrgUnit } from '@/features/tenant-admin/organisation/hooks';
import { changedFields, fieldErrorsOf, orNull } from '@/features/tenant-admin/organisation/organisation-presentation';
import type { OrgUnit } from '@/features/tenant-admin/organisation/types';
import { useTeams } from '@/features/tenant-admin/teams/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';

// Departments (design/screens/admin-organisation.html, TEN-02, TEN-S8): the org
// units of kind business area, business unit or function, each with its head,
// the unit it sits in and how many teams sit in it. Any member reads them; Add
// and Edit show for vocab.manage, which the server checks again. No step-up and
// no second person: a department grants no access. A department is deactivated,
// never deleted, and its kind is plain meta text because this card adds no pill slot.

const DEPARTMENT_KINDS = ['business_area', 'business_unit', 'function'] as const;
type DepartmentKind = (typeof DEPARTMENT_KINDS)[number];

const isDepartment = (unit: Pick<OrgUnit, 'kind'>): boolean => (DEPARTMENT_KINDS as readonly string[]).includes(unit.kind);

function kindLabel(kind: DepartmentKind, t: Translate): string {
  switch (kind) {
    case 'business_area':
      return t('admin.org.departments.kind.businessArea');
    case 'business_unit':
      return t('admin.org.departments.kind.businessUnit');
    case 'function':
      return t('admin.org.departments.kind.function');
  }
}

const asKind = (value: string): DepartmentKind => DEPARTMENT_KINDS.find((kind) => kind === value) ?? 'business_area';

export function DepartmentsSection() {
  const t = useT();
  const units = useOrgUnits();
  const teams = useTeams();
  const canEdit = useCanEditOrganisation();
  const [editing, setEditing] = useState<OrgUnit | 'new' | null>(null);

  const all = units.data ?? [];
  const departments = all.filter(isDepartment);
  const nameOf = (id: string | null) => all.find((unit) => unit.id === id)?.name;
  const teamCount = (id: string) => (teams.data ?? []).filter((team) => team.active && team.orgUnitId === id).length;

  return (
    <Panel title={t('admin.org.departments.title')} data-org-section="departments">
      <p className="mb-3 text-muted">{t('admin.org.departments.lede')}</p>
      {units.isPending ? (
        <LoadingState />
      ) : units.isError ? (
        <ErrorState title={t('admin.org.departments.errorTitle')} onRetry={() => void units.refetch()} />
      ) : departments.length === 0 ? (
        <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-empty-state="">
          <h3 className="text-fg">{t('admin.org.departments.emptyTitle')}</h3>
          <p className="mx-auto mt-2 max-w-[60ch]">{t('admin.org.departments.emptyBody')}</p>
        </div>
      ) : (
        <Rows>
          {departments.map((unit) => {
            const parent = nameOf(unit.parentId);
            return (
              <Row key={unit.id} className={unit.active ? undefined : 'opacity-60'} data-department={unit.name}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3>{unit.name}</h3>
                    <Meta>
                      <span>{kindLabel(asKind(unit.kind), t)}</span>
                      {parent !== undefined ? <span>{t('admin.org.departments.in', { name: parent })}</span> : null}
                      <span>{unit.head === null ? t('admin.org.departments.noHead') : t('admin.org.departments.head', { name: unit.head.name })}</span>
                      <span>{t('admin.org.departments.teamCount', { count: teamCount(unit.id) })}</span>
                      {unit.active ? null : <span>{t('admin.org.entities.inactive')}</span>}
                    </Meta>
                  </div>
                  {canEdit ? (
                    <Button variant="ghost" size="small" onClick={() => setEditing(unit)} aria-label={t('admin.org.editNamed', { name: unit.name })}>
                      {t('admin.org.edit')}
                    </Button>
                  ) : null}
                </div>
              </Row>
            );
          })}
        </Rows>
      )}
      {canEdit ? (
        <ButtonBar>
          <Button size="small" onClick={() => setEditing('new')}>
            {t('admin.org.departments.add')}
          </Button>
        </ButtonBar>
      ) : null}
      {editing !== null ? <DepartmentForm unit={editing === 'new' ? null : editing} units={all} onClose={() => setEditing(null)} /> : null}
    </Panel>
  );
}

const FIELDS = ['kind', 'name', 'parentId', 'headUserId', 'active'] as const;

function DepartmentForm({ unit, units, onClose }: { unit: OrgUnit | null; units: readonly OrgUnit[]; onClose: () => void }) {
  const t = useT();
  const create = useCreateOrgUnit();
  const update = useUpdateOrgUnit();
  const write = unit === null ? create : update;
  const [draft, setDraft] = useState({
    kind: asKind(unit?.kind ?? 'business_area'),
    name: unit?.name ?? '',
    parentId: unit?.parentId ?? '',
    headUserId: unit?.head?.id ?? '',
    active: unit?.active ?? true,
  });
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const errors = fieldErrorsOf(write.error, FIELDS, { unknown_member: 'headUserId' });
  // A department sits under any other active unit, never under itself.
  const parents = units.filter((u) => u.id !== unit?.id && (u.active || u.id === unit?.parentId));

  const submit = () => {
    if (unit === null) {
      create.mutate(
        { kind: draft.kind, name: draft.name.trim(), parentId: orNull(draft.parentId), headUserId: orNull(draft.headUserId), orgNumber: '', lei: '', countryCode: '', entityTerm: null },
        { onSuccess: onClose },
      );
      return;
    }
    const before = { name: unit.name, parentId: unit.parentId, headUserId: unit.head?.id ?? null, active: unit.active };
    const body = changedFields({ name: draft.name.trim(), parentId: draft.parentId, headUserId: draft.headUserId, active: draft.active }, before);
    update.mutate({ id: unit.id, body, version: unit.version }, { onSuccess: onClose });
  };

  return (
    <DialogForm title={unit === null ? t('admin.org.departments.addTitle') : t('admin.org.editNamed', { name: unit.name })} error={write.error} formLevel={errors.formLevel} pending={write.isPending} onSubmit={submit} onClose={onClose}>
      {unit === null ? (
        <Field id="department-kind" label={t('admin.org.form.kind')} error={errors.fields.kind}>
          <Select id="department-kind" value={draft.kind} onChange={(e) => set('kind', asKind(e.target.value))}>
            {DEPARTMENT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kindLabel(kind, t)}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      <Field id="department-name" label={t('admin.org.form.name')} error={errors.fields.name}>
        <TextInput id="department-name" value={draft.name} onChange={(e) => set('name', e.target.value)} aria-invalid={errors.fields.name !== undefined} />
      </Field>
      <Field id="department-parent" label={t('admin.org.entities.parent')} error={errors.fields.parentId}>
        <Select id="department-parent" value={draft.parentId} onChange={(e) => set('parentId', e.target.value)}>
          {/* A unit at the top stays there: a change cannot lift it out from under its parent. */}
          <option value="" disabled={unit?.parentId != null}>
            {t('admin.org.entities.top')}
          </option>
          {parents.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
      </Field>
      <PersonSelect id="department-head" label={t('admin.org.departments.headLabel')} hint={t('admin.org.departments.headHint')} error={errors.fields.headUserId} value={draft.headUserId} current={unit?.head ?? null} onChange={(id) => set('headUserId', id)} />
      {unit !== null ? (
        <Field id="department-active" label={t('admin.org.entities.activeLabel')} error={errors.fields.active}>
          <Select id="department-active" value={draft.active ? 'active' : 'inactive'} onChange={(e) => set('active', e.target.value === 'active')}>
            <option value="active">{t('admin.org.entities.activeOption')}</option>
            <option value="inactive">{t('admin.org.entities.inactiveOption')}</option>
          </Select>
        </Field>
      ) : null}
    </DialogForm>
  );
}
