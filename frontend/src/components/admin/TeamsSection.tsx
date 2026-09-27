'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { DialogForm } from '@/features/tenant-admin/organisation/fields';
import { useCanEditOrganisation, useOrgUnits } from '@/features/tenant-admin/organisation/hooks';
import { fieldErrorsOf } from '@/features/tenant-admin/organisation/organisation-presentation';
import { teamLabels, type Team } from '@/features/tenant-admin/teams/api';
import { useCreateTeam, useRenameTeam, useTeams } from '@/features/tenant-admin/teams/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// Teams (design/screens/admin-organisation.html, TEN-03, TEN-S8): each team with
// its department and how many active members it has. A team is a row of the
// bank's own `team` list, so Add and Rename write that list under vocab.manage,
// which the server checks again; retiring and merging one is the list's own
// screen. Who is in a team is set on the member, under members.manage.

export function TeamsSection() {
  const t = useT();
  const teams = useTeams();
  const units = useOrgUnits();
  const canEdit = useCanEditOrganisation();
  const [editing, setEditing] = useState<Team | 'new' | null>(null);
  const departmentOf = (id: string | null) => (units.data ?? []).find((unit) => unit.id === id)?.name;

  return (
    <Panel title={t('admin.org.teams.title')} data-org-section="teams">
      <p className="mb-3 text-muted">{t('admin.org.teams.lede')}</p>
      {teams.isPending ? (
        <LoadingState />
      ) : teams.isError ? (
        <ErrorState title={t('admin.org.teams.errorTitle')} onRetry={() => void teams.refetch()} />
      ) : (
        <Rows>
          {teams.data.map((team) => {
            const department = departmentOf(team.orgUnitId);
            return (
              <Row key={team.key} className={team.active ? undefined : 'opacity-60'} data-team={team.key}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3>{team.label}</h3>
                    <Meta>
                      {department !== undefined ? <span>{department}</span> : null}
                      <span>{t('admin.org.teams.memberCount', { count: team.memberCount })}</span>
                      {team.active ? null : <span>{t('admin.org.teams.retired')}</span>}
                    </Meta>
                  </div>
                  {canEdit ? (
                    <Button variant="ghost" size="small" onClick={() => setEditing(team)} aria-label={t('admin.org.teams.renameNamed', { name: team.label })}>
                      {t('admin.org.teams.rename')}
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
            {t('admin.org.teams.add')}
          </Button>
        </ButtonBar>
      ) : null}
      {editing !== null ? <TeamForm team={editing === 'new' ? null : editing} onClose={() => setEditing(null)} /> : null}
    </Panel>
  );
}

function TeamForm({ team, onClose }: { team: Team | null; onClose: () => void }) {
  const t = useT();
  const create = useCreateTeam();
  const rename = useRenameTeam();
  const write = team === null ? create : rename;
  // The list's own row carries every label and the version a rename sends as If-Match.
  const row = useVocabularyValues('team', true, team !== null).data?.find((value) => value.key === team?.key);
  // A field nobody has typed in shows the row's own label once it has loaded.
  const [nameEn, setNameEn] = useState<string | null>(null);
  const [nameSv, setNameSv] = useState<string | null>(null);
  const [blank, setBlank] = useState(false);
  const name = nameEn ?? row?.labels.en ?? team?.label ?? '';
  const sv = nameSv ?? row?.labels.sv ?? '';
  const errors = fieldErrorsOf(write.error, []);

  const submit = () => {
    if (name.trim() === '') {
      setBlank(true);
      return;
    }
    setBlank(false);
    const labels = teamLabels(name, sv);
    if (team === null) create.mutate(labels, { onSuccess: onClose });
    else rename.mutate({ key: team.key, labels, version: row?.version }, { onSuccess: onClose });
  };

  return (
    <DialogForm title={team === null ? t('admin.org.teams.addTitle') : t('admin.org.teams.renameNamed', { name: team.label })} error={write.error} formLevel={errors.formLevel} pending={write.isPending} onSubmit={submit} onClose={onClose}>
      <Field id="team-name" label={t('admin.org.teams.name')} error={blank ? t('admin.org.teams.nameRequired') : undefined}>
        <TextInput id="team-name" value={name} onChange={(e) => setNameEn(e.target.value)} aria-invalid={blank} />
      </Field>
      <Field id="team-name-sv" label={t('admin.org.teams.nameSv')} hint={t('admin.org.teams.nameSvHint')}>
        <TextInput id="team-name-sv" value={sv} onChange={(e) => setNameSv(e.target.value)} />
      </Field>
    </DialogForm>
  );
}
