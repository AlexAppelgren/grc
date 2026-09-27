'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { DialogForm, PersonSelect, TermPicker, TermSelect } from '@/features/tenant-admin/organisation/fields';
import { useCanEditOrganisation, useCreateLicence, useCreateOrgUnit, useLicences, useOrgUnits, useScopeTermGroups, useUpdateLicence, useUpdateOrgUnit } from '@/features/tenant-admin/organisation/hooks';
import {
  changedFields,
  entityTree,
  fieldErrorsOf,
  isCertificate,
  isWithdrawn,
  legalEntities,
  orNull,
  presentEntity,
  presentServices,
} from '@/features/tenant-admin/organisation/organisation-presentation';
import type { Licence, OrgUnit } from '@/features/tenant-admin/organisation/types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// Legal entities, and the licences and certificates each one holds
// (design/screens/admin-organisation.html, TEN-02, TEN-S2, TEN-S10). Any
// member reads them; Add and Edit show for vocab.manage, which the server
// checks again. No step-up and no second person: none of this grants access.
// A unit is deactivated and a licence withdrawn, never deleted, and a
// certificate carries no term, so it changes no obligation.

// The shared library's legal-entity dimension: the one an entity is scoped with.
const ENTITY_DIMENSION = 'legal_entity';

function countryName(code: string, ctx: FormatContext): string {
  try {
    return new Intl.DisplayNames([ctx.locale], { type: 'region' }).of(code) ?? code;
  } catch {
    return code;
  }
}

function unitKindLabel(kind: OrgUnit['kind'], t: Translate): string {
  return kind === 'group' ? t('admin.org.entities.kind.group') : t('admin.org.entities.kind.legalEntity');
}

export function EntitiesSection() {
  const t = useT();
  const ctx = useFormatContext();
  const units = useOrgUnits();
  const canEdit = useCanEditOrganisation();
  const [editing, setEditing] = useState<OrgUnit | 'new' | null>(null);

  const rows = entityTree(units.data ?? []);
  return (
    <>
      <Panel title={t('admin.org.entities.title')} data-org-section="entities">
        <p className="mb-3 text-muted">{t('admin.org.entities.lede')}</p>
        {units.isPending ? (
          <LoadingState />
        ) : units.isError ? (
          <ErrorState title={t('admin.org.entities.errorTitle')} onRetry={() => void units.refetch()} />
        ) : rows.length === 0 ? (
          <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-empty-state="">
            <h3 className="text-fg">{t('admin.org.entities.emptyTitle')}</h3>
            <p className="mx-auto mt-2 max-w-[60ch]">{t('admin.org.entities.emptyBody')}</p>
          </div>
        ) : (
          <Rows>
            {rows.map(({ unit, depth }) => (
              <Row key={unit.id} className={unit.active ? undefined : 'opacity-60'} style={{ marginInlineStart: `${depth * 20}px` }} data-org-unit={unit.name}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3>{unit.name}</h3>
                    <Meta>
                      <span>{unitKindLabel(unit.kind, t)}</span>
                      {unit.orgNumber !== '' ? <span className="font-mono">{unit.orgNumber}</span> : null}
                      {unit.kind === 'legal_entity' ? <span className={unit.lei === '' ? undefined : 'font-mono'}>{unit.lei === '' ? t('admin.org.entities.noLei') : t('admin.org.entities.lei', { lei: unit.lei })}</span> : null}
                      {unit.countryCode !== '' ? <span>{countryName(unit.countryCode, ctx)}</span> : null}
                      {unit.active ? null : <span>{t('admin.org.entities.inactive')}</span>}
                    </Meta>
                    <div className="mt-1.5">
                      <PillRow pills={presentEntity(unit)} />
                    </div>
                  </div>
                  {canEdit ? (
                    <Button variant="ghost" size="small" onClick={() => setEditing(unit)} aria-label={t('admin.org.editNamed', { name: unit.name })}>
                      {t('admin.org.edit')}
                    </Button>
                  ) : null}
                </div>
              </Row>
            ))}
          </Rows>
        )}
        {canEdit ? (
          <ButtonBar>
            <Button size="small" onClick={() => setEditing('new')}>
              {t('admin.org.entities.add')}
            </Button>
          </ButtonBar>
        ) : null}
      </Panel>
      <LicencesPanel entities={legalEntities(units.data ?? [])} canEdit={canEdit} />
      {editing !== null ? <EntityForm unit={editing === 'new' ? null : editing} units={units.data ?? []} onClose={() => setEditing(null)} /> : null}
    </>
  );
}

const UNIT_FIELDS = ['kind', 'name', 'parentId', 'orgNumber', 'lei', 'countryCode', 'entityTerm', 'active'] as const;

function EntityForm({ unit, units, onClose }: { unit: OrgUnit | null; units: readonly OrgUnit[]; onClose: () => void }) {
  const t = useT();
  const create = useCreateOrgUnit();
  const update = useUpdateOrgUnit();
  const write = unit === null ? create : update;
  const groups = useScopeTermGroups(ENTITY_DIMENSION);
  const [kind, setKind] = useState<'group' | 'legal_entity'>(unit?.kind === 'group' ? 'group' : 'legal_entity');
  const [draft, setDraft] = useState({
    name: unit?.name ?? '',
    parentId: unit?.parentId ?? '',
    orgNumber: unit?.orgNumber ?? '',
    lei: unit?.lei ?? '',
    countryCode: unit?.countryCode ?? '',
    entityTerm: unit?.entityTerm?.key ?? '',
    active: unit?.active ?? true,
  });
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const errors = fieldErrorsOf(write.error, UNIT_FIELDS, { unknown_key: 'entityTerm' });
  const isEntity = kind === 'legal_entity';
  // A unit may sit under any other group or entity, never under itself.
  const parents = units.filter((u) => (u.kind === 'group' || u.kind === 'legal_entity') && u.id !== unit?.id);

  const submit = () => {
    // A group carries none of a legal entity's fields.
    const entity = {
      orgNumber: isEntity ? draft.orgNumber.trim() : '',
      lei: isEntity ? draft.lei.trim().toUpperCase() : '',
      countryCode: isEntity ? draft.countryCode.trim().toUpperCase() : '',
      entityTerm: isEntity ? draft.entityTerm : '',
    };
    if (unit === null) {
      create.mutate({ kind, name: draft.name.trim(), parentId: orNull(draft.parentId), ...entity, entityTerm: orNull(entity.entityTerm) }, { onSuccess: onClose });
      return;
    }
    const before = { name: unit.name, parentId: unit.parentId, orgNumber: unit.orgNumber, lei: unit.lei, countryCode: unit.countryCode, entityTerm: unit.entityTerm?.key ?? null, active: unit.active };
    const body = changedFields({ name: draft.name.trim(), parentId: draft.parentId, ...entity, active: draft.active }, before, isEntity ? ['orgNumber', 'lei', 'countryCode'] : []);
    update.mutate({ id: unit.id, body, version: unit.version }, { onSuccess: onClose });
  };

  return (
    <DialogForm title={unit === null ? t('admin.org.entities.addTitle') : t('admin.org.editNamed', { name: unit.name })} error={write.error} formLevel={errors.formLevel} pending={write.isPending} onSubmit={submit} onClose={onClose}>
      {unit === null ? (
        <Field id="unit-kind" label={t('admin.org.form.kind')} error={errors.fields.kind}>
          <Select id="unit-kind" value={kind} onChange={(e) => setKind(e.target.value === 'group' ? 'group' : 'legal_entity')}>
            <option value="legal_entity">{t('admin.org.entities.kind.legalEntity')}</option>
            <option value="group">{t('admin.org.entities.kind.group')}</option>
          </Select>
        </Field>
      ) : null}
      <Field id="unit-name" label={t('admin.org.form.name')} error={errors.fields.name}>
        <TextInput id="unit-name" value={draft.name} onChange={(e) => set('name', e.target.value)} aria-invalid={errors.fields.name !== undefined} />
      </Field>
      <Field id="unit-parent" label={t('admin.org.entities.parent')} error={errors.fields.parentId}>
        <Select id="unit-parent" value={draft.parentId} onChange={(e) => set('parentId', e.target.value)}>
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
      {isEntity ? (
        <>
          <div className="grid gap-x-4 md:grid-cols-2">
            <Field id="unit-org-number" label={t('admin.org.entities.orgNumber')} error={errors.fields.orgNumber}>
              <TextInput id="unit-org-number" className="font-mono" value={draft.orgNumber} onChange={(e) => set('orgNumber', e.target.value)} />
            </Field>
            <Field id="unit-lei" label={t('admin.org.entities.leiLabel')} hint={t('admin.org.entities.leiHint')} error={errors.fields.lei}>
              <TextInput id="unit-lei" className="font-mono" maxLength={20} value={draft.lei} onChange={(e) => set('lei', e.target.value)} />
            </Field>
          </div>
          <div className="grid gap-x-4 md:grid-cols-2">
            <Field id="unit-country" label={t('admin.org.entities.country')} hint={t('admin.org.entities.countryHint')} error={errors.fields.countryCode}>
              <TextInput id="unit-country" maxLength={2} value={draft.countryCode} onChange={(e) => set('countryCode', e.target.value)} />
            </Field>
            <TermSelect id="unit-term" label={t('admin.org.entities.term')} error={errors.fields.entityTerm} groups={groups} value={draft.entityTerm} onChange={(key) => set('entityTerm', key)} />
          </div>
        </>
      ) : null}
      {unit !== null ? (
        <Field id="unit-active" label={t('admin.org.entities.activeLabel')} error={errors.fields.active}>
          <Select id="unit-active" value={draft.active ? 'active' : 'inactive'} onChange={(e) => set('active', e.target.value === 'active')}>
            <option value="active">{t('admin.org.entities.activeOption')}</option>
            <option value="inactive">{t('admin.org.entities.inactiveOption')}</option>
          </Select>
        </Field>
      ) : null}
    </DialogForm>
  );
}

function LicencesPanel({ entities, canEdit }: { entities: readonly OrgUnit[]; canEdit: boolean }) {
  const t = useT();
  if (entities.length === 0) return null;
  return (
    <Panel title={t('admin.org.licences.title')} data-org-section="licences">
      <p className="mb-3 text-muted">{t('admin.org.licences.lede')}</p>
      {entities.map((entity) => (
        <EntityLicences key={entity.id} entity={entity} canEdit={canEdit} />
      ))}
    </Panel>
  );
}

function EntityLicences({ entity, canEdit }: { entity: OrgUnit; canEdit: boolean }) {
  const t = useT();
  const licences = useLicences(entity.id);
  const [showWithdrawn, setShowWithdrawn] = useState(false);
  const [editing, setEditing] = useState<Licence | 'new' | null>(null);
  const all = licences.data ?? [];
  const withdrawn = all.filter(isWithdrawn);
  const shown = showWithdrawn ? all : all.filter((licence) => !isWithdrawn(licence));

  return (
    <section className="mb-4" aria-label={entity.name} data-licences-of={entity.name}>
      <h3 className="mb-2 text-muted">{entity.name}</h3>
      {licences.isPending ? (
        <LoadingState rows={1} />
      ) : licences.isError ? (
        <ErrorState title={t('admin.org.licences.errorTitle')} onRetry={() => void licences.refetch()} />
      ) : shown.length === 0 ? (
        <p className="text-meta text-muted">{t('admin.org.licences.none')}</p>
      ) : (
        <Rows>
          {shown.map((licence) => (
            <LicenceRow key={licence.id} licence={licence} onEdit={canEdit && !isWithdrawn(licence) ? () => setEditing(licence) : undefined} />
          ))}
        </Rows>
      )}
      <ButtonBar>
        {withdrawn.length > 0 ? (
          <Button variant="ghost" size="small" aria-pressed={showWithdrawn} onClick={() => setShowWithdrawn((v) => !v)}>
            {showWithdrawn ? t('admin.org.licences.hideWithdrawn') : t('admin.org.licences.showWithdrawn', { count: withdrawn.length })}
          </Button>
        ) : null}
        {canEdit ? (
          <Button size="small" onClick={() => setEditing('new')} aria-label={t('admin.org.licences.addTo', { name: entity.name })}>
            {t('admin.org.licences.add')}
          </Button>
        ) : null}
      </ButtonBar>
      {editing !== null ? <LicenceForm entity={entity} licence={editing === 'new' ? null : editing} onClose={() => setEditing(null)} /> : null}
    </section>
  );
}

function Detail({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted">{term}</dt>
      <dd className="m-0">{children}</dd>
    </>
  );
}

function LicenceRow({ licence, onEdit }: { licence: Licence; onEdit?: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const certificate = isCertificate(licence);
  const date = (value: string | null) => (value === null ? null : formatDate(value, ctx));
  return (
    <Row className={isWithdrawn(licence) ? 'opacity-60' : undefined} data-licence={licence.licenceType.key} data-withdrawn={isWithdrawn(licence) ? '' : undefined}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3>{licence.licenceType.label}</h3>
          <Meta>
            <span>{certificate ? t('admin.org.licences.kind.certificate') : t('admin.org.licences.kind.licence')}</span>
            {licence.issuer !== '' ? <span>{licence.issuer}</span> : null}
            {isWithdrawn(licence) ? <span>{t('admin.org.licences.withdrawnOn', { date: date(licence.withdrawnOn) ?? '' })}</span> : null}
          </Meta>
          <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-meta">
            {licence.reference !== '' ? <Detail term={t('admin.org.licences.reference')}>{licence.reference}</Detail> : null}
            {licence.number !== '' ? <Detail term={t('admin.org.licences.number')}>{licence.number}</Detail> : null}
            {licence.scopeStatement !== '' ? <Detail term={t('admin.org.licences.scopeStatement')}>{licence.scopeStatement}</Detail> : null}
            {licence.grantedOn !== null ? <Detail term={t('admin.org.licences.grantedOn')}>{date(licence.grantedOn)}</Detail> : null}
            {licence.issuedOn !== null ? <Detail term={t('admin.org.licences.issuedOn')}>{date(licence.issuedOn)}</Detail> : null}
            {licence.validUntil !== null ? <Detail term={t('admin.org.licences.validUntil')}>{date(licence.validUntil)}</Detail> : null}
            {licence.nextAuditOn !== null ? <Detail term={t('admin.org.licences.nextAuditOn')}>{date(licence.nextAuditOn)}</Detail> : null}
            {licence.owner !== null ? <Detail term={t('admin.org.licences.owner')}>{licence.owner.name}</Detail> : null}
            {licence.serviceTerms.length > 0 ? (
              <Detail term={t('admin.org.licences.services')}>
                <PillRow pills={presentServices(licence)} />
              </Detail>
            ) : null}
            {licence.scopeNote !== '' ? <Detail term={t('admin.org.licences.scopeNote')}>{licence.scopeNote}</Detail> : null}
          </dl>
        </div>
        {onEdit !== undefined ? (
          <Button variant="ghost" size="small" onClick={onEdit} aria-label={t('admin.org.editNamed', { name: licence.licenceType.label })}>
            {t('admin.org.edit')}
          </Button>
        ) : null}
      </div>
    </Row>
  );
}

const LICENCE_FIELDS = ['licenceType', 'reference', 'grantedOn', 'withdrawnOn', 'scopeNote', 'issuer', 'number', 'scopeStatement', 'issuedOn', 'validUntil', 'nextAuditOn', 'ownerUserId', 'serviceTerms'] as const;
const LICENCE_ONLY = ['reference', 'grantedOn', 'scopeNote', 'serviceTerms'] as const;
const CERTIFICATE_ONLY = ['issuer', 'number', 'scopeStatement', 'issuedOn', 'validUntil', 'nextAuditOn'] as const;

function LicenceForm({ entity, licence, onClose }: { entity: OrgUnit; licence: Licence | null; onClose: () => void }) {
  const t = useT();
  const create = useCreateLicence(entity.id);
  const update = useUpdateLicence(entity.id);
  const write = licence === null ? create : update;
  const groups = useScopeTermGroups();
  const [certificate, setCertificate] = useState(licence !== null && isCertificate(licence));
  const [draft, setDraft] = useState({
    licenceType: licence?.licenceType.key ?? '',
    reference: licence?.reference ?? '',
    grantedOn: licence?.grantedOn ?? '',
    withdrawnOn: licence?.withdrawnOn ?? '',
    scopeNote: licence?.scopeNote ?? '',
    issuer: licence?.issuer ?? '',
    number: licence?.number ?? '',
    scopeStatement: licence?.scopeStatement ?? '',
    issuedOn: licence?.issuedOn ?? '',
    validUntil: licence?.validUntil ?? '',
    nextAuditOn: licence?.nextAuditOn ?? '',
    ownerUserId: licence?.owner?.id ?? '',
    serviceTerms: licence?.serviceTerms.map((term) => term.key) ?? [],
  });
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft((current) => ({ ...current, [key]: value }));
  // An unknown term is the services' when any are chosen, else the type's.
  const errors = fieldErrorsOf(write.error, LICENCE_FIELDS, { unknown_member: 'ownerUserId', unknown_key: draft.serviceTerms.length > 0 ? 'serviceTerms' : 'licenceType' });

  const submit = () => {
    // Only the fields of the chosen kind are sent: the other kind's are blank.
    const blank = (keys: readonly string[], on: boolean) => (on ? Object.fromEntries(keys.map((key) => [key, key === 'serviceTerms' ? [] : ''])) : {});
    const shown: typeof draft = { ...draft, ...blank(LICENCE_ONLY, certificate), ...blank(CERTIFICATE_ONLY, !certificate), ...(certificate ? {} : { ownerUserId: '' }) };
    if (licence === null) {
      const day = (value: string) => orNull(value);
      create.mutate(
        {
          ...shown,
          grantedOn: day(shown.grantedOn),
          withdrawnOn: day(shown.withdrawnOn),
          issuedOn: day(shown.issuedOn),
          validUntil: day(shown.validUntil),
          nextAuditOn: day(shown.nextAuditOn),
          ownerUserId: orNull(shown.ownerUserId),
        },
        { onSuccess: onClose },
      );
      return;
    }
    const before = { ...licence, licenceType: licence.licenceType.key, ownerUserId: licence.owner?.id ?? null, serviceTerms: licence.serviceTerms.map((term) => term.key) };
    const body = changedFields(shown, before, certificate ? ['issuer', 'number', 'scopeStatement'] : ['reference', 'scopeNote']);
    update.mutate({ id: licence.id, body, version: licence.version }, { onSuccess: onClose });
  };

  const text = (key: 'reference' | 'number' | 'issuer', label: string) => (
    <Field id={`licence-${key}`} label={label} error={errors.fields[key]}>
      <TextInput id={`licence-${key}`} value={draft[key]} onChange={(e) => set(key, e.target.value)} aria-invalid={errors.fields[key] !== undefined} />
    </Field>
  );
  const day = (key: 'grantedOn' | 'withdrawnOn' | 'issuedOn' | 'validUntil' | 'nextAuditOn', label: string, hint?: string) => (
    <Field id={`licence-${key}`} label={label} hint={hint} error={errors.fields[key]}>
      <TextInput id={`licence-${key}`} type="date" value={draft[key]} onChange={(e) => set(key, e.target.value)} aria-invalid={errors.fields[key] !== undefined} />
    </Field>
  );
  const long = (key: 'scopeNote' | 'scopeStatement', label: string) => (
    <Field id={`licence-${key}`} label={label} error={errors.fields[key]}>
      <TextArea id={`licence-${key}`} value={draft[key]} onChange={(e) => set(key, e.target.value)} aria-invalid={errors.fields[key] !== undefined} />
    </Field>
  );

  return (
    <DialogForm
      title={licence === null ? t('admin.org.licences.addTitle', { name: entity.name }) : t('admin.org.editNamed', { name: licence.licenceType.label })}
      error={write.error}
      formLevel={errors.formLevel}
      pending={write.isPending}
      onSubmit={submit}
      onClose={onClose}
    >
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field id="licence-kind" label={t('admin.org.form.kind')}>
          <Select id="licence-kind" value={certificate ? 'certificate' : 'licence'} disabled={licence !== null} onChange={(e) => setCertificate(e.target.value === 'certificate')}>
            <option value="licence">{t('admin.org.licences.kind.licence')}</option>
            <option value="certificate">{t('admin.org.licences.kind.certificate')}</option>
          </Select>
        </Field>
        <TermSelect id="licence-licenceType" label={t('admin.org.licences.type')} error={errors.fields.licenceType} groups={groups} value={draft.licenceType} onChange={(key) => set('licenceType', key)} />
      </div>
      {certificate ? (
        <>
          <div className="grid gap-x-4 md:grid-cols-2">
            {text('issuer', t('admin.org.licences.issuer'))}
            {text('number', t('admin.org.licences.number'))}
          </div>
          {long('scopeStatement', t('admin.org.licences.scopeStatement'))}
          <div className="grid gap-x-4 md:grid-cols-2">
            {day('issuedOn', t('admin.org.licences.issuedOn'))}
            {day('validUntil', t('admin.org.licences.validUntil'))}
          </div>
          <div className="grid gap-x-4 md:grid-cols-2">
            {day('nextAuditOn', t('admin.org.licences.nextAuditOn'))}
            <PersonSelect id="licence-ownerUserId" label={t('admin.org.licences.owner')} hint={t('admin.org.licences.ownerHint')} error={errors.fields.ownerUserId} value={draft.ownerUserId} current={licence?.owner ?? null} onChange={(id) => set('ownerUserId', id)} />
          </div>
        </>
      ) : (
        <>
          <div className="grid gap-x-4 md:grid-cols-2">
            {text('reference', t('admin.org.licences.reference'))}
            {day('grantedOn', t('admin.org.licences.grantedOn'))}
          </div>
          <TermPicker id="licence-serviceTerms" label={t('admin.org.licences.services')} hint={t('admin.org.licences.servicesHint')} error={errors.fields.serviceTerms} groups={groups} value={draft.serviceTerms} onChange={(keys) => set('serviceTerms', keys)} />
          {long('scopeNote', t('admin.org.licences.scopeNote'))}
        </>
      )}
      {day('withdrawnOn', t('admin.org.licences.withdrawnLabel'), t('admin.org.licences.withdrawnHint'))}
    </DialogForm>
  );
}
