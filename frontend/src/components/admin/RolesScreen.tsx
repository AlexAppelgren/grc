'use client';

import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useCreateRole, usePermissionsReference, useRetireRole, useRoles, useUpdateRole } from '@/features/tenant-admin/hooks';
import { humaniseKey, presentPermissions, presentRole } from '@/features/tenant-admin/members-presentation';
import type { PermissionRef, TenantRole } from '@/features/tenant-admin/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// Roles from permissions (design/screens/admin-roles.html, ID-09): a role is
// a row of permission constants; the editor lists the constants from
// GET /reference/permissions. System roles can be relabelled, not changed.

const PILLS_SHOWN = 6;

type Editing = { mode: 'create' } | { mode: 'edit'; role: TenantRole } | { mode: 'rename'; role: TenantRole } | null;

function groupPermissions(permissions: readonly PermissionRef[]): [string, PermissionRef[]][] {
  const groups = new Map<string, PermissionRef[]>();
  for (const permission of permissions) {
    const list = groups.get(permission.group) ?? [];
    list.push(permission);
    groups.set(permission.group, list);
  }
  return [...groups.entries()];
}

function RoleForm({ editing, onClose }: { editing: NonNullable<Editing>; onClose: () => void }) {
  const t = useT();
  const reference = usePermissionsReference();
  const create = useCreateRole();
  const update = useUpdateRole();
  const role = editing.mode === 'create' ? null : editing.role;
  const labelsOnly = editing.mode === 'rename';
  const [key, setKey] = useState(role?.key ?? '');
  const [labelEn, setLabelEn] = useState(role?.labels.en ?? '');
  const [labelSv, setLabelSv] = useState(role?.labels.sv ?? '');
  const [usageNote, setUsageNote] = useState(role?.usageNote ?? '');
  const [permissions, setPermissions] = useState<string[]>(role?.permissions ?? []);
  const [problem, setProblem] = useState<'key' | 'permissions' | null>(null);
  const pending = create.isPending || update.isPending;
  const error = create.error ?? update.error;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!labelsOnly && (key.trim() === '' || labelEn.trim() === '')) {
      setProblem('key');
      return;
    }
    if (!labelsOnly && permissions.length === 0) {
      setProblem('permissions');
      return;
    }
    setProblem(null);
    const labels = { en: labelEn.trim(), sv: labelSv.trim() };
    if (role === null) {
      create.mutate({ key: key.trim(), labels, usageNote: usageNote.trim(), permissions }, { onSuccess: onClose });
      return;
    }
    const changed = permissions.length !== role.permissions.length || permissions.some((p) => !role.permissions.includes(p));
    update.mutate(
      { key: role.key, body: labelsOnly ? { labels } : { labels, usageNote: usageNote.trim(), ...(changed ? { permissions } : {}) } },
      { onSuccess: onClose },
    );
  };

  return (
    <form onSubmit={submit} noValidate aria-busy={pending}>
      <Panel title={role === null ? t('admin.roles.create') : t('admin.roles.editTitle')} data-role-form="">
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="role-key" label={t('admin.roles.key')} hint={t('admin.roles.keyHint')}>
            <TextInput id="role-key" placeholder={t('admin.roles.keyPlaceholder')} value={key} disabled={role !== null} onChange={(e) => setKey(e.target.value)} />
          </Field>
          <Field id="role-usage-note" label={t('admin.roles.usageNote')}>
            <TextInput id="role-usage-note" placeholder={t('admin.roles.usageNotePlaceholder')} value={usageNote} disabled={labelsOnly} onChange={(e) => setUsageNote(e.target.value)} />
          </Field>
          <Field id="role-label-en" label={t('admin.roles.labelEn')} error={problem === 'key' ? t('admin.roles.keyRequired') : undefined}>
            <TextInput id="role-label-en" placeholder={t('admin.roles.labelEnPlaceholder')} value={labelEn} onChange={(e) => setLabelEn(e.target.value)} />
          </Field>
          <Field id="role-label-sv" label={t('admin.roles.labelSv')}>
            <TextInput id="role-label-sv" placeholder={t('admin.roles.labelSvPlaceholder')} value={labelSv} onChange={(e) => setLabelSv(e.target.value)} />
          </Field>
        </div>
        {labelsOnly ? null : (
          <CheckGroup legend={t('admin.roles.permissions')} hint={t('admin.roles.stepUp')} error={problem === 'permissions' ? t('admin.roles.permissionsRequired') : undefined}>
            {reference.isPending ? <StatusLine>{t('common.loading')}</StatusLine> : null}
            {reference.isError ? <ProblemAlert error={reference.error} /> : null}
            {groupPermissions(reference.data ?? []).map(([group, list]) => (
              <div key={group} className="mt-3.5">
                <h3 className="microlabel mb-1 text-muted">{humaniseKey(group)}</h3>
                {list.map((permission) => (
                  <CheckRow
                    key={permission.key}
                    id={`role-permission-${permission.key}`}
                    label={humaniseKey(permission.key)}
                    hint={permission.description}
                    checked={permissions.includes(permission.key)}
                    onChange={(checked) => setPermissions((current) => (checked ? [...current, permission.key] : current.filter((k) => k !== permission.key)))}
                  />
                ))}
              </div>
            ))}
          </CheckGroup>
        )}
        {error !== null && error !== undefined ? <ProblemAlert error={error} codes={{ step_up_required: t('problem.stepUpCancelled') }} /> : null}
        <ButtonBar>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={pending}>
            {role === null ? t('admin.roles.createButton') : t('admin.roles.saveButton')}
          </Button>
        </ButtonBar>
      </Panel>
    </form>
  );
}

function RoleRow({ role, onEdit }: { role: TenantRole; onEdit: (editing: Editing) => void }) {
  const t = useT();
  const retire = useRetireRole();
  const [confirming, setConfirming] = useState(false);
  const permissionPills = presentPermissions(role.permissions);
  const shown = permissionPills.slice(0, PILLS_SHOWN);
  const hidden = permissionPills.length - shown.length;
  return (
    <Row data-role-key={role.key}>
      <h3 className="mb-1 flex flex-wrap items-center gap-2 font-semibold">
        <span>{role.label}</span>
        <PillRow pills={presentRole(role, t)} />
      </h3>
      <Meta>
        <code className="font-mono">{role.key}</code>
        {role.usageNote.length > 0 ? <span>{role.usageNote}</span> : null}
      </Meta>
      <div className="mt-2">
        <PillRow pills={shown}>{hidden > 0 ? <span className="text-meta text-muted">{t('admin.roles.more', { count: hidden })}</span> : null}</PillRow>
      </div>
      {retire.isError ? <ProblemAlert error={retire.error} /> : null}
      {confirming ? <StatusLine>{t('admin.roles.retireConfirm')}</StatusLine> : null}
      {role.active ? (
        <ButtonBar>
          {role.isSystem ? (
            <Button variant="ghost" size="small" onClick={() => onEdit({ mode: 'rename', role })}>
              {t('admin.roles.rename')}
            </Button>
          ) : confirming ? (
            <>
              <Button variant="ghost" size="small" onClick={() => setConfirming(false)}>
                {t('common.cancel')}
              </Button>
              <Button variant="danger" size="small" disabled={retire.isPending} onClick={() => retire.mutate(role.key, { onSettled: () => setConfirming(false) })}>
                {t('admin.roles.retire')}
              </Button>
            </>
          ) : (
            <>
              <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
                {t('admin.roles.retire')}
              </Button>
              <Button variant="ghost" size="small" onClick={() => onEdit({ mode: 'edit', role })}>
                {t('admin.roles.edit')}
              </Button>
            </>
          )}
        </ButtonBar>
      ) : null}
    </Row>
  );
}

export function RolesScreen() {
  const t = useT();
  const roles = useRoles();
  const [editing, setEditing] = useState<Editing>(null);

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.roles.title')} lede={t('admin.roles.lede')} actions={<Button onClick={() => setEditing({ mode: 'create' })}>{t('admin.roles.create')}</Button>} />
      {editing !== null ? <RoleForm key={editing.mode === 'create' ? 'create' : `${editing.mode}:${editing.role.key}`} editing={editing} onClose={() => setEditing(null)} /> : null}
      {roles.isPending ? (
        <LoadingState rows={3} />
      ) : roles.isError ? (
        <ErrorState title={t('admin.roles.errorTitle')} onRetry={() => void roles.refetch()} />
      ) : roles.data.length === 0 ? (
        <EmptyState title={t('admin.roles.emptyTitle')} body={t('admin.roles.emptyBody')} />
      ) : (
        <Rows data-roles-list="">
          {roles.data.map((role) => (
            <RoleRow key={role.key} role={role} onEdit={setEditing} />
          ))}
        </Rows>
      )}
    </>
  );
}
