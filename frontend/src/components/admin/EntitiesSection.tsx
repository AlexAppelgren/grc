'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckRow, Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { FOOTPRINT_REQUEST } from '@/features/footprint/footprint-presentation';
import { useFormatContext } from '@/features/identity/hooks';
import { DialogForm, PersonSelect, TermPicker, TermSelect } from '@/features/tenant-admin/organisation/fields';
import {
  useApplyRegisterLookup,
  useAuthorities,
  useCanEditOrganisation,
  useCreateLicence,
  useCreateOrgUnit,
  useOrgUnits,
  useRegisterLookup,
  useScopeTermGroups,
  useStartRegisterLookup,
  useUpdateLicence,
  useUpdateOrgUnit,
} from '@/features/tenant-admin/organisation/hooks';
import {
  appliedMessage,
  applyLabel,
  branchesLine,
  businessLine,
  changedFields,
  entityTree,
  fieldErrorsOf,
  isCertificate,
  isChosen,
  isWithdrawn,
  legalEntities,
  lookupChoice,
  lookupError,
  lookupReadLine,
  lookupStatus,
  orNull,
  presentEntity,
  presentServices,
} from '@/features/tenant-admin/organisation/organisation-presentation';
import type { Licence, OrgUnit, OrgUnitRow, RegisterLookupEntity } from '@/features/tenant-admin/organisation/types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// Legal entities, and the licences and certificates each one holds
// (design/screens/admin-organisation.html, TEN-02, TEN-S2, TEN-S10). Any
// member reads them; Add and Edit show for vocab.manage, which the server
// checks again. No step-up and no second person: none of this grants access.
// A unit is deactivated and a licence withdrawn, never deleted, and a
// certificate carries no term, so it changes no obligation.
// "Fill in from public registers" (TEN-07, TEN-S13, PUBLIC_REGISTERS.md 3.1) needs
// vocab.manage too and no step-up: the number starts a job, the dialog polls it, and nothing
// is written until the person adds the ticked companies. An entity read from a register
// shows the register's facts as the register writes them, with the date of the last read.

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
  const canSeeScope = (usePermissions() ?? []).includes(FOOTPRINT_REQUEST);
  const [editing, setEditing] = useState<OrgUnit | 'new' | null>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const [applied, setApplied] = useState<string | null>(null);

  const rows = entityTree(units.data ?? []);
  const actions = (className?: string) =>
    canEdit ? (
      <ButtonBar className={className}>
        <Button variant="ghost" size="small" onClick={() => setLookingUp(true)}>
          {t('admin.org.registers.title')}
        </Button>
        <Button size="small" onClick={() => setEditing('new')}>
          {t('admin.org.entities.add')}
        </Button>
      </ButtonBar>
    ) : null;
  return (
    <>
      <Panel title={t('admin.org.entities.title')} data-org-section="entities">
        <p className="mb-3 text-muted">{t('admin.org.entities.lede')}</p>
        {applied !== null ? (
          <StatusLine tone="positive">
            {applied}{' '}
            {canSeeScope ? (
              <Link href="/admin/footprint" className="underline">
                {t('admin.org.registers.scopeLink')}
              </Link>
            ) : null}
          </StatusLine>
        ) : null}
        {units.isPending ? (
          <LoadingState />
        ) : units.isError ? (
          <ErrorState title={t('admin.org.entities.errorTitle')} onRetry={() => void units.refetch()} />
        ) : rows.length === 0 ? (
          <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-empty-state="">
            <h3 className="text-fg">{t('admin.org.entities.emptyTitle')}</h3>
            <p className="mx-auto mt-2 max-w-[60ch]">{t('admin.org.entities.emptyBody')}</p>
            {actions('justify-center')}
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
                    <RegisterFacts unit={unit} />
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
        {rows.length > 0 ? actions() : null}
      </Panel>
      <LicencesPanel entities={legalEntities(units.data ?? [])} canEdit={canEdit} />
      {editing !== null ? <EntityForm unit={editing === 'new' ? null : editing} units={units.data ?? []} onClose={() => setEditing(null)} /> : null}
      {lookingUp ? (
        <RegisterLookupDialog
          onClose={() => setLookingUp(false)}
          onApplied={(message) => {
            setLookingUp(false);
            setApplied(message);
          }}
        />
      ) : null}
    </>
  );
}

/** What the register says about an entity (state "register-facts"): its businesses, its licences behind a disclosure, its branches, what the scope does not use, and the exclusions an approved scope request gave it. */
function RegisterFacts({ unit }: { unit: OrgUnitRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const [licencesShown, setLicencesShown] = useState(false);
  const entry = unit.registerEntry;
  const outside = unit.scopeExclusions ?? [];
  if (entry === null && outside.length === 0) return null;
  const facts = entry?.facts;
  const licencesId = `register-licences-${unit.id}`;
  return (
    <>
      <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-meta" data-register-facts="">
        {facts !== undefined && businessLine(facts) !== '' ? <Detail term={t('admin.org.registers.business')}>{businessLine(facts)}</Detail> : null}
        {facts !== undefined && facts.licences.length > 0 ? (
          <Detail term={t('admin.org.registers.licences')}>
            <Button variant="ghost" size="small" aria-expanded={licencesShown} aria-controls={licencesId} onClick={() => setLicencesShown((shown) => !shown)}>
              {licencesShown ? t('admin.org.registers.hideLicences') : t('admin.org.registers.showLicences', { count: facts.licences.length })}
            </Button>
            <ul id={licencesId} hidden={!licencesShown} className="m-0 mt-1 grid list-none gap-1 p-0">
              {facts.licences.map((licence, i) => (
                <li key={`${i}:${licence.text}`}>
                  {licence.text}
                  {licence.grantedOn !== null ? <span className="ml-2 text-muted">{formatDate(licence.grantedOn, ctx)}</span> : null}
                </li>
              ))}
            </ul>
          </Detail>
        ) : null}
        {facts !== undefined && facts.branches.length > 0 ? <Detail term={t('admin.org.registers.branches')}>{branchesLine(facts.branches, t)}</Detail> : null}
        {entry !== null && entry.unmapped.length > 0 ? (
          <Detail term={t('admin.org.registers.unmapped')}>
            <span className="font-mono">{entry.unmapped.join(' · ')}</span>
          </Detail>
        ) : null}
        {outside.length > 0 ? <Detail term={t('admin.org.registers.outside')}>{outside.map((term) => term.label).join(', ')}</Detail> : null}
      </dl>
      {entry !== null ? <p className="mt-1 text-meta text-muted">{t('admin.org.registers.readAt', { authority: entry.authority.name, date: formatDate(entry.readAt, ctx) })}</p> : null}
    </>
  );
}

/** One company found, its facts as the register writes them; the bank's own is ticked and cannot be unticked. */
function LookupCompany({ entity, authorityName, chosen, disabled, onToggle }: { entity: RegisterLookupEntity; authorityName: string; chosen: boolean; disabled: boolean; onToggle: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const status = lookupStatus(entity, authorityName, t);
  return (
    // The wrapper carries the row's rule, since each row is the last child of its own wrapper.
    <div data-lookup-company={entity.name} className="border-b border-line last:border-b-0">
      <CheckRow
        id={`lookup-${entity.lei}`}
        label={entity.name}
        checked={chosen}
        disabled={disabled || entity.existingOrgUnitId !== null}
        onChange={onToggle}
        hint={
          <span className="flex flex-wrap gap-x-2">
            {entity.registrationNumber !== '' ? <span className="font-mono">{entity.registrationNumber}</span> : null}
            {entity.country !== '' ? <span>{countryName(entity.country, ctx)}</span> : null}
            {entity.facts !== null ? <span>{entity.facts.mainBusiness}</span> : null}
            {entity.facts !== null ? <span>{t('admin.org.registers.licenceCount', { count: entity.facts.licences.length })}</span> : null}
            {status !== null ? <span>{status}</span> : null}
          </span>
        }
      />
    </div>
  );
}

const LOOKUP_QUERY = 'register-query';

/**
 * The number, then "Reading the registers…" while the job runs, then the companies as a
 * checklist (design/screens/admin-organisation.html). A failed job says why in the screen's
 * own words, by its code, and the number can be typed again.
 */
function RegisterLookupDialog({ onClose, onApplied }: { onClose: () => void; onApplied: (message: string) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const start = useStartRegisterLookup();
  const [lookupId, setLookupId] = useState<string | null>(null);
  const job = useRegisterLookup(lookupId);
  const apply = useApplyRegisterLookup();
  const authorities = useAuthorities();
  const [query, setQuery] = useState('');
  // The companies the person ticked or unticked against what the register suggests.
  const [flipped, setFlipped] = useState<ReadonlySet<string>>(new Set());

  const lookup = job.data ?? start.data ?? null;
  const running = lookup !== null && (lookup.status === 'queued' || lookup.status === 'running');
  const found = lookup?.status === 'succeeded' && lookup.entities.length > 0 ? lookup : null;
  const authorityName = (key: string) => authorities.data?.find((authority) => authority.key === key)?.name ?? key;

  const lookUp = (event: FormEvent) => {
    event.preventDefault();
    start.mutate(query.trim(), {
      onSuccess: (created) => {
        setFlipped(new Set());
        setLookupId(created.id);
      },
    });
  };

  if (found !== null) {
    const choice = lookupChoice(found.entities, flipped);
    const flip = (lei: string) =>
      setFlipped((current) => {
        const next = new Set(current);
        if (!next.delete(lei)) next.add(lei);
        return next;
      });
    const submit = (event: FormEvent) => {
      event.preventDefault();
      apply.mutate({ lookupId: found.id, leis: choice.leis }, { onSuccess: (done) => onApplied(appliedMessage(done, t)) });
    };
    const readLine = lookupReadLine(found, authorityName, t, ctx);
    return (
      <Modal open onOpenChange={(open) => !open && !apply.isPending && onClose()} title={t('admin.org.registers.groupTitle', { name: found.entities[0]?.name ?? '' })}>
        <form onSubmit={submit} noValidate aria-busy={apply.isPending} data-lookup-result="">
          <div className="grid">
            {found.entities.map((entity) => (
              <LookupCompany
                key={entity.lei}
                entity={entity}
                authorityName={entity.authority === null ? '' : authorityName(entity.authority)}
                chosen={isChosen(entity, flipped)}
                disabled={apply.isPending}
                onToggle={() => flip(entity.lei)}
              />
            ))}
          </div>
          {readLine !== null ? <p className="mt-2 text-meta text-muted">{readLine}</p> : null}
          {apply.isError ? <ProblemAlert error={apply.error} /> : null}
          <ButtonBar>
            <Button variant="outline" onClick={onClose} disabled={apply.isPending}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={choice.leis.length === 0 || apply.isPending}>
              {applyLabel(choice, t)}
            </Button>
          </ButtonBar>
        </form>
      </Modal>
    );
  }

  return (
    <Modal open onOpenChange={(open) => !open && onClose()} title={t('admin.org.registers.title')}>
      <form onSubmit={lookUp} noValidate aria-busy={running || start.isPending}>
        <Field id={LOOKUP_QUERY} label={t('admin.org.registers.query')} hint={t('admin.org.registers.queryHint')}>
          <TextInput id={LOOKUP_QUERY} className="font-mono" placeholder={t('admin.org.registers.queryPlaceholder')} value={query} aria-describedby={`${LOOKUP_QUERY}-hint`} onChange={(e) => setQuery(e.target.value)} />
        </Field>
        {running ? <StatusLine>{t('admin.org.registers.reading')}</StatusLine> : null}
        {lookup?.status === 'failed' && lookup.error !== null ? (
          <p role="alert" className="mt-2.5 text-meta text-negative" data-lookup-error={lookup.error}>
            {lookupError(lookup.error, t)}
          </p>
        ) : null}
        {start.isError ? <ProblemAlert error={start.error} /> : null}
        {job.isError ? <ProblemAlert error={job.error} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={query.trim() === '' || running || start.isPending}>
            {t('admin.org.registers.lookUp')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
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

function LicencesPanel({ entities, canEdit }: { entities: readonly OrgUnitRow[]; canEdit: boolean }) {
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

function EntityLicences({ entity, canEdit }: { entity: OrgUnitRow; canEdit: boolean }) {
  const t = useT();
  const [showWithdrawn, setShowWithdrawn] = useState(false);
  const [editing, setEditing] = useState<Licence | 'new' | null>(null);
  const all = entity.licences;
  const withdrawn = all.filter(isWithdrawn);
  const shown = showWithdrawn ? all : all.filter((licence) => !isWithdrawn(licence));

  return (
    <section className="mb-4" aria-label={entity.name} data-licences-of={entity.name}>
      <h3 className="mb-2 text-muted">{entity.name}</h3>
      {shown.length === 0 ? (
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
  const update = useUpdateLicence();
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
