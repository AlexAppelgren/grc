'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { FormDialog } from '@/components/ui/Dialogs';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { useFormatContext } from '@/features/identity/hooks';
import { orgFormCodes, PersonSelect, TermPicker, TermSelect } from '@/features/tenant-admin/organisation/fields';
import { useCreateLicence, useScopeTermGroups, useUpdateLicence } from '@/features/tenant-admin/organisation/hooks';
import { changedFields, fieldErrorsOf, isCertificate, isWithdrawn, orNull, presentServices } from '@/features/tenant-admin/organisation/organisation-presentation';
import type { Licence, OrgUnit, OrgUnitRow } from '@/features/tenant-admin/organisation/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// The licences and certificates a bank recorded for one legal entity (TEN-02, TEN-S2,
// TEN-S10), on the Licences page. Any member reads them; Add and Edit show for
// vocab.manage, which the server checks again. No step-up and no second person: none of
// this grants access. A licence is withdrawn, never deleted, and a certificate carries no
// term, so it changes no obligation.

/** The licences and certificates recorded for one entity, Add beside the heading and withdrawn ones behind Show withdrawn. `none` says what an empty list means here; without a heading it stands in the heading's place. */
export function EntityLicences({ entity, canEdit, title, none }: { entity: OrgUnitRow; canEdit: boolean; title: string | null; none: string }) {
  const t = useT();
  const [showWithdrawn, setShowWithdrawn] = useState(false);
  const [editing, setEditing] = useState<Licence | 'new' | null>(null);
  const all = entity.licences;
  const withdrawn = all.filter(isWithdrawn);
  const shown = showWithdrawn ? all : all.filter((licence) => !isWithdrawn(licence));

  return (
    <section className="mt-4" data-licences-of={entity.name}>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1.5">
        {title !== null ? <h3>{title}</h3> : <p className="text-meta text-muted">{none}</p>}
        {canEdit ? (
          <Button size="small" className="ml-auto" onClick={() => setEditing('new')} aria-label={t('admin.org.licences.addTo', { name: entity.name })}>
            {t('admin.org.licences.add')}
          </Button>
        ) : null}
      </div>
      {shown.length > 0 ? (
        <Rows>
          {shown.map((licence) => (
            <LicenceRow key={licence.id} licence={licence} onEdit={canEdit && !isWithdrawn(licence) ? () => setEditing(licence) : undefined} />
          ))}
        </Rows>
      ) : title !== null ? (
        <p className="text-meta text-muted">{none}</p>
      ) : null}
      {withdrawn.length > 0 ? (
        <ButtonBar>
          <Button variant="ghost" size="small" aria-pressed={showWithdrawn} onClick={() => setShowWithdrawn((v) => !v)}>
            {showWithdrawn ? t('admin.org.licences.hideWithdrawn') : t('admin.org.licences.showWithdrawn', { count: withdrawn.length })}
          </Button>
        </ButtonBar>
      ) : null}
      {editing !== null ? <LicenceForm entity={entity} licence={editing === 'new' ? null : editing} onClose={() => setEditing(null)} /> : null}
    </section>
  );
}

/** A term and its value in a definition list. */
export function Detail({ term, children }: { term: string; children: React.ReactNode }) {
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
          <h4 className="font-semibold">{licence.licenceType.label}</h4>
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
    <FormDialog title={licence === null ? t('admin.org.licences.addTitle', { name: entity.name }) : t('admin.org.editNamed', { name: licence.licenceType.label })} submitLabel={t('common.save')} pending={write.isPending} error={errors.formLevel ? write.error : undefined} codes={orgFormCodes(t)} onSubmit={submit} onClose={onClose}>
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
    </FormDialog>
  );
}
