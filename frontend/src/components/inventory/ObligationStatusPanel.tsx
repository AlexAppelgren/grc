'use client';

import { useState, type FormEvent } from 'react';

import { Facts, type Fact } from '@/components/inventory/ObligationPanels';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { isStaleWrite, usePeople, useRegisterEntry, useReloadRegister, useUpdateRegister, useUpdateRegisterEntity } from '@/features/register/hooks';
import { presentCompliance, presentComplianceHeader } from '@/features/register/register-presentation';
import type { RegisterEntityPatch, RegisterEntityStatus, RegisterEntry, RegisterPatch, RegisterVocabRef } from '@/features/register/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// "Where we stand" and "How we handle it" (REG-02, D-42). Per legal entity where
// the obligation applies to several, each row with its own pill, note, risk,
// owner (a person or a team, never both), process, system, evidence location and
// next review; else the obligation's own. The header's pill is the server's
// worst of the entities it applies to, with the entity named beside it. No status
// is asked where it does not apply; the last one stays in the history. Edits
// need register.edit and send only what changed, with the version last read: a
// row someone else saved in between is refused and nothing is merged.

const EDIT_PERMISSION = 'register.edit';
// The server's limits (apps/register/schemas.py NOTE_MAX, NAME_MAX).
const NOTE_MAX = 4000;
const NAME_MAX = 500;

/** Which row a dialog edits: one legal entity, the obligation's own standing, or how it is handled. */
type Editing = { kind: 'entity'; entity: RegisterEntityStatus } | { kind: 'whole' } | { kind: 'handle' };

/** A form's values as the controls hold them; an owner picker's value is `person:<id>` or `team:<key>`. */
interface Values {
  status: string;
  rationale: string;
  note: string;
  risk: string;
  owner: string;
  team: string;
  contact: string;
  process: string;
  system: string;
  evidence: string;
  review: string;
}

const PERSON = 'person:';
const TEAM = 'team:';

function valuesOf(entry: RegisterEntry, editing: Editing): Values {
  const row = editing.kind === 'entity' ? editing.entity : entry;
  const owner = editing.kind === 'entity' ? editing.entity.owner : entry.firstLineOwner;
  const team = editing.kind === 'entity' ? editing.entity.ownerTeam : null;
  return {
    status: row.complianceStatus.key,
    rationale: '',
    note: row.statusNote ?? '',
    risk: row.riskRating?.key ?? '',
    owner: owner !== null ? `${PERSON}${owner.id}` : team !== null ? `${TEAM}${team.key}` : '',
    team: entry.ownerTeam?.key ?? '',
    contact: entry.complianceContact?.id ?? '',
    process: row.process ?? '',
    system: row.system ?? '',
    evidence: row.evidenceLocation ?? '',
    review: row.nextReviewDate ?? '',
  };
}

/**
 * The body of a save: only the fields that moved. A text emptied clears it; a
 * key, a person or a date the server cannot clear is sent only when chosen.
 */
export function changesOf(before: Values, after: Values, editing: Editing): RegisterPatch & RegisterEntityPatch {
  const body: RegisterPatch & RegisterEntityPatch = {};
  const moved = (field: keyof Values) => after[field] !== before[field];
  const chosen = (field: keyof Values) => moved(field) && after[field] !== '';
  if (editing.kind !== 'handle') {
    if (chosen('status')) {
      body.complianceStatus = after.status;
      if (after.rationale.trim() !== '') body.rationale = after.rationale.trim();
    }
    if (moved('note')) body.statusNote = after.note;
    if (chosen('risk')) body.riskRating = after.risk;
    if (chosen('review')) body.nextReviewDate = after.review;
    if (chosen('owner')) {
      const id = after.owner.slice(after.owner.indexOf(':') + 1);
      if (after.owner.startsWith(TEAM)) body.ownerTeam = id;
      else if (editing.kind === 'entity') body.ownerId = id;
      else body.firstLineOwnerId = id;
    }
  }
  if (editing.kind === 'whole') {
    if (chosen('team')) body.ownerTeam = after.team;
    if (chosen('contact')) body.complianceContactId = after.contact;
  }
  if (editing.kind !== 'whole') {
    if (moved('process')) body.process = after.process;
    if (moved('system')) body.system = after.system;
    if (moved('evidence')) body.evidenceLocation = after.evidence;
  }
  return body;
}

function ownerText(person: { name: string } | null, team: RegisterVocabRef | null, t: Translate): string | null {
  if (person !== null) return person.name;
  return team === null ? null : t('obligationStatus.team', { team: team.label });
}

function standing(row: RegisterEntityStatus | RegisterEntry, t: Translate, ctx: FormatContext): Fact[] {
  const entity = 'orgUnitId' in row;
  const facts: [string, string, string | null][] = [
    ['note', t('obligationStatus.statusNote'), row.statusNote],
    ['risk', t('obligationStatus.risk'), row.riskRating?.label ?? null],
    entity
      ? ['owner', t('obligationStatus.owner'), ownerText(row.owner, row.ownerTeam, t)]
      : ['owner', t('obligationStatus.firstLineOwner'), row.firstLineOwner?.name ?? null],
    ...(entity
      ? ([
          ['process', t('obligationStatus.process'), row.process],
          ['system', t('obligationStatus.system'), row.system],
          ['evidence', t('obligationStatus.evidence'), row.evidenceLocation],
        ] as [string, string, string | null][])
      : ([
          ['team', t('obligationStatus.ownerTeam'), row.ownerTeam?.label ?? null],
          ['contact', t('obligationStatus.contact'), row.complianceContact?.name ?? null],
        ] as [string, string, string | null][])),
    ['review', t('obligationStatus.nextReview'), row.nextReviewDate === null ? null : formatDate(row.nextReviewDate, ctx)],
  ];
  return facts.flatMap(([key, label, value]) => (value === null || value === '' ? [] : [{ key, label, value }]));
}

export function ObligationStatusPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const canEdit = (usePermissions() ?? []).includes(EDIT_PERMISSION);
  const entry = useRegisterEntry(obligationId);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [saved, setSaved] = useState(false);

  if (entry.isError) {
    return (
      <Panel title={t('obligationStatus.heading')} data-status-panel="">
        <ErrorState title={t('obligationStatus.errorTitle')} onRetry={() => void entry.refetch()} />
      </Panel>
    );
  }
  if (entry.data === undefined) return <LoadingState rows={2} />;

  const data = entry.data;
  const header = presentComplianceHeader(data, t);
  const applying = data.entities.filter((entity) => entity.applicability === 'applies');
  const answers = data.entities.length > 0 ? data.entities : [data];
  const edit = (next: Editing) => (canEdit ? (
    <ButtonBar className="mt-2 justify-start">
      <Button
        variant="ghost"
        size="small"
        onClick={() => {
          setSaved(false);
          setEditing(next);
        }}
      >
        {t('obligationStatus.edit')}
      </Button>
    </ButtonBar>
  ) : null);
  const handled: Fact[] = (
    [
      ['process', t('obligationStatus.process'), data.process],
      ['system', t('obligationStatus.system'), data.system],
      ['evidence', t('obligationStatus.evidence'), data.evidenceLocation],
    ] as const
  ).map(([key, label, value]) => ({ key, label, value: value ?? t('obligationStatus.notMapped') }));

  return (
    <>
      <Panel title={t('obligationStatus.heading')} data-status-panel="">
        {header === null ? (
          <p className="text-meta text-muted" data-status-not-asked="">
            {answers.some((answer) => answer.applicability === 'not_applicable') ? t('obligationStatus.notAsked') : t('obligationStatus.notYet')}
          </p>
        ) : (
          <div className="mb-2.5" data-status-header="">
            <Meta>
              <PillRow pills={[header.pill]} />
              {header.weakest === null ? null : <span>{header.weakest}</span>}
            </Meta>
          </div>
        )}
        {applying.length > 0 ? (
          <Rows>
            {applying.map((entity) => (
              <Row key={entity.orgUnitId} data-status-row={entity.orgUnitId}>
                <Meta>
                  <PillRow pills={[presentCompliance(entity.complianceStatus)]} />
                </Meta>
                <h3 className="my-1.5">{entity.orgUnitName}</h3>
                <Facts facts={standing(entity, t, ctx)} />
                {edit({ kind: 'entity', entity })}
              </Row>
            ))}
          </Rows>
        ) : header === null ? null : (
          <div data-status-row="whole">
            <Facts facts={standing(data, t, ctx)} />
            {edit({ kind: 'whole' })}
          </div>
        )}
        {saved ? <StatusLine tone="positive">{t('obligationStatus.saved')}</StatusLine> : null}
      </Panel>
      <Panel title={t('obligationStatus.handleHeading')} data-handle-panel="">
        <Facts facts={handled} />
        {edit({ kind: 'handle' })}
      </Panel>
      {editing === null ? null : (
        <EditDialog
          obligationId={obligationId}
          entry={data}
          editing={editing}
          onClose={(stored) => {
            setEditing(null);
            setSaved(stored);
          }}
        />
      )}
    </>
  );
}

/** A picker's rows: the active ones, and the one the record holds even once retired or gone. */
function withCurrent<T extends { key: string } | { id: string }>(rows: readonly T[], current: T | null): readonly T[] {
  const idOf = (row: T) => ('key' in row ? row.key : row.id);
  return current === null || rows.some((row) => idOf(row) === idOf(current)) ? rows : [current, ...rows];
}

function EditDialog({ obligationId, entry, editing, onClose }: { obligationId: string; entry: RegisterEntry; editing: Editing; onClose: (stored: boolean) => void }) {
  const t = useT();
  const standingForm = editing.kind !== 'handle';
  const statuses = useVocabularyValues('compliance_status', false, standingForm);
  const risks = useVocabularyValues('risk_rating', false, standingForm);
  const teams = useVocabularyValues('team', false, standingForm);
  const people = usePeople(standingForm);
  const saveWhole = useUpdateRegister(obligationId);
  const saveEntity = useUpdateRegisterEntity(obligationId);
  const reload = useReloadRegister();
  const [before] = useState(() => valuesOf(entry, editing));
  const [values, setValues] = useState(before);
  const save = editing.kind === 'entity' ? saveEntity : saveWhole;
  const row = editing.kind === 'entity' ? editing.entity : entry;
  const set = (field: keyof Values) => (event: { target: { value: string } }) => setValues({ ...values, [field]: event.target.value });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body = changesOf(before, values, editing);
    if (Object.keys(body).length === 0) return onClose(false);
    const done = { onSuccess: () => onClose(true) };
    if (editing.kind === 'entity') saveEntity.mutate({ orgUnitId: editing.entity.orgUnitId, body, version: editing.entity.version }, done);
    else saveWhole.mutate({ body, version: entry.version }, done);
  };

  const title =
    editing.kind === 'handle'
      ? t('obligationStatus.handleHeading')
      : editing.kind === 'entity'
        ? t('obligationStatus.editTitle', { entity: editing.entity.orgUnitName })
        : t('obligationStatus.heading');
  const members = people.data ?? [];
  const teamRows = teams.data ?? [];
  const owner = editing.kind === 'entity' ? editing.entity.owner : entry.firstLineOwner;

  return (
    <Modal open onOpenChange={(stay) => (stay ? undefined : onClose(false))} title={title}>
      <form onSubmit={submit} noValidate aria-busy={save.isPending}>
        {standingForm ? (
          <>
            <Field id="status-value" label={t('obligationStatus.status')} hint={t('obligationStatus.statusHint')}>
              <Select id="status-value" value={values.status} onChange={set('status')}>
                {withCurrent<{ key: string; label: string }>(statuses.data ?? [], row.complianceStatus).map((status) => (
                  <option key={status.key} value={status.key}>
                    {status.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id="status-rationale" label={t('obligationStatus.rationale')}>
              <TextArea id="status-rationale" value={values.rationale} maxLength={NOTE_MAX} onChange={set('rationale')} />
            </Field>
            <Field id="status-note" label={t('obligationStatus.statusNote')}>
              <TextArea id="status-note" value={values.note} maxLength={NOTE_MAX} onChange={set('note')} />
            </Field>
            <Field id="status-risk" label={t('obligationStatus.risk')}>
              <Select id="status-risk" value={values.risk} onChange={set('risk')}>
                {before.risk === '' ? <option value="">{t('obligationStatus.notSet')}</option> : null}
                {withCurrent<{ key: string; label: string }>(risks.data ?? [], row.riskRating).map((risk) => (
                  <option key={risk.key} value={risk.key}>
                    {risk.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id="status-owner"
              label={editing.kind === 'entity' ? t('obligationStatus.owner') : t('obligationStatus.firstLineOwner')}
              hint={editing.kind === 'entity' ? t('obligationStatus.ownerHint') : undefined}
            >
              <Select id="status-owner" value={values.owner} onChange={set('owner')}>
                {before.owner === '' ? <option value="">{t('obligationStatus.notSet')}</option> : null}
                <optgroup label={t('obligationStatus.people')}>
                  {withCurrent(members, owner).map((person) => (
                    <option key={person.id} value={`${PERSON}${person.id}`}>
                      {person.name}
                    </option>
                  ))}
                </optgroup>
                {editing.kind === 'entity' ? (
                  <optgroup label={t('obligationStatus.teams')}>
                    {withCurrent<{ key: string; label: string }>(teamRows, editing.entity.ownerTeam).map((team) => (
                      <option key={team.key} value={`${TEAM}${team.key}`}>
                        {team.label}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
              </Select>
            </Field>
            {editing.kind === 'whole' ? (
              <>
                <Field id="status-team" label={t('obligationStatus.ownerTeam')}>
                  <Select id="status-team" value={values.team} onChange={set('team')}>
                    {before.team === '' ? <option value="">{t('obligationStatus.notSet')}</option> : null}
                    {withCurrent<{ key: string; label: string }>(teamRows, entry.ownerTeam).map((team) => (
                      <option key={team.key} value={team.key}>
                        {team.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field id="status-contact" label={t('obligationStatus.contact')}>
                  <Select id="status-contact" value={values.contact} onChange={set('contact')}>
                    {before.contact === '' ? <option value="">{t('obligationStatus.notSet')}</option> : null}
                    {withCurrent(members, entry.complianceContact).map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            ) : null}
            <Field id="status-review" label={t('obligationStatus.nextReview')}>
              <TextInput id="status-review" type="date" value={values.review} onChange={set('review')} />
            </Field>
          </>
        ) : null}
        {editing.kind === 'whole' ? null : (
          <>
            <Field id="status-process" label={t('obligationStatus.process')}>
              <TextInput id="status-process" value={values.process} maxLength={NAME_MAX} onChange={set('process')} />
            </Field>
            <Field id="status-system" label={t('obligationStatus.system')}>
              <TextInput id="status-system" value={values.system} maxLength={NAME_MAX} onChange={set('system')} />
            </Field>
            <Field id="status-evidence" label={t('obligationStatus.evidence')}>
              <TextInput id="status-evidence" value={values.evidence} maxLength={NAME_MAX} onChange={set('evidence')} />
            </Field>
          </>
        )}
        {save.isError ? (
          isStaleWrite(save.error) ? (
            <div role="alert" className="mt-2.5 text-meta text-negative" data-stale-write="">
              {t('obligationStatus.stale')}
              <ButtonBar className="mt-2 justify-start">
                <Button
                  variant="outline"
                  size="small"
                  onClick={() => {
                    void reload();
                    onClose(false);
                  }}
                >
                  {t('obligationStatus.reload')}
                </Button>
              </ButtonBar>
            </div>
          ) : (
            <ProblemAlert error={save.error} />
          )
        ) : null}
        <ButtonBar>
          <Button variant="outline" onClick={() => onClose(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {t('common.save')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}
