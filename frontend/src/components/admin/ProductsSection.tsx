'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { DialogForm, PersonSelect, TermPicker } from '@/features/tenant-admin/organisation/fields';
import { useCanEditOrganisation, useCreateProduct, useOrgUnits, useProducts, useScopeTermGroups, useUpdateProduct } from '@/features/tenant-admin/organisation/hooks';
import { changedFields, fieldErrorsOf, legalEntities, orNull, presentProductScope } from '@/features/tenant-admin/organisation/organisation-presentation';
import type { OrgUnit, Product, ProductStatus } from '@/features/tenant-admin/organisation/types';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// Products, scoped with the same terms as obligations
// (design/screens/admin-organisation.html, TEN-02, TEN-S2). Status is plain
// meta text; the entity and the terms are the scope block's brand pills. A
// product is retired, never deleted, and a retired one is dimmed.

const STATUS_LABEL: Record<ProductStatus, MessageKey> = {
  planned: 'admin.org.products.status.planned',
  live: 'admin.org.products.status.live',
  retired: 'admin.org.products.status.retired',
};
const STATUSES = Object.keys(STATUS_LABEL) as ProductStatus[];

export function ProductsSection() {
  const t = useT();
  const ctx = useFormatContext();
  const products = useProducts();
  const units = useOrgUnits();
  const canEdit = useCanEditOrganisation();
  const [editing, setEditing] = useState<Product | 'new' | null>(null);
  const unitById = new Map((units.data ?? []).map((unit) => [unit.id, unit]));

  return (
    <Panel title={t('admin.org.products.title')} data-org-section="products">
      <p className="mb-3 text-muted">{t('admin.org.products.lede')}</p>
      {products.isPending ? (
        <LoadingState />
      ) : products.isError ? (
        <ErrorState title={t('admin.org.products.errorTitle')} onRetry={() => void products.refetch()} />
      ) : products.data.length === 0 ? (
        <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-empty-state="">
          <h3 className="text-fg">{t('admin.org.products.emptyTitle')}</h3>
          <p className="mx-auto mt-2 max-w-[60ch]">{t('admin.org.products.emptyBody')}</p>
        </div>
      ) : (
        <Rows>
          {products.data.map((product) => (
            <Row key={product.id} className={product.status === 'retired' ? 'opacity-60' : undefined} data-product={product.name}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <h3>{product.name}</h3>
                  {product.description !== '' ? <p className="mb-1">{product.description}</p> : null}
                  <Meta>
                    <span>{t(STATUS_LABEL[product.status])}</span>
                    {product.launchDate !== null ? (
                      <span>{t(product.status === 'planned' ? 'admin.org.products.launch' : 'admin.org.products.launched', { date: formatDate(product.launchDate, ctx) })}</span>
                    ) : null}
                    {product.owner !== null ? <span>{t('admin.org.products.ownerIs', { name: product.owner.name })}</span> : null}
                  </Meta>
                  <div className="mt-1.5">
                    <PillRow pills={presentProductScope(product, product.orgUnitId === null ? undefined : unitById.get(product.orgUnitId))} />
                  </div>
                </div>
                {canEdit ? (
                  <Button variant="ghost" size="small" onClick={() => setEditing(product)} aria-label={t('admin.org.editNamed', { name: product.name })}>
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
            {t('admin.org.products.add')}
          </Button>
        </ButtonBar>
      ) : null}
      {editing !== null ? <ProductForm product={editing === 'new' ? null : editing} entities={legalEntities(units.data ?? [])} onClose={() => setEditing(null)} /> : null}
    </Panel>
  );
}

const PRODUCT_FIELDS = ['name', 'description', 'status', 'launchDate', 'orgUnitId', 'ownerUserId', 'terms'] as const;

function ProductForm({ product, entities, onClose }: { product: Product | null; entities: readonly OrgUnit[]; onClose: () => void }) {
  const t = useT();
  const create = useCreateProduct();
  const update = useUpdateProduct();
  const write = product === null ? create : update;
  const groups = useScopeTermGroups();
  const [draft, setDraft] = useState({
    name: product?.name ?? '',
    description: product?.description ?? '',
    status: product?.status ?? ('live' as ProductStatus),
    launchDate: product?.launchDate ?? '',
    orgUnitId: product?.orgUnitId ?? '',
    ownerUserId: product?.owner?.id ?? '',
    terms: product?.terms.map((term) => term.key) ?? [],
  });
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const errors = fieldErrorsOf(write.error, PRODUCT_FIELDS, { unknown_member: 'ownerUserId', unknown_key: 'terms' });

  const submit = () => {
    const values = { ...draft, name: draft.name.trim() };
    if (product === null) {
      create.mutate(
        { ...values, launchDate: orNull(values.launchDate), orgUnitId: orNull(values.orgUnitId), ownerUserId: orNull(values.ownerUserId) },
        { onSuccess: onClose },
      );
      return;
    }
    const before = { ...product, ownerUserId: product.owner?.id ?? null, terms: product.terms.map((term) => term.key) };
    update.mutate({ id: product.id, body: changedFields(values, before, ['description']), version: product.version }, { onSuccess: onClose });
  };

  return (
    <DialogForm title={product === null ? t('admin.org.products.addTitle') : t('admin.org.editNamed', { name: product.name })} error={write.error} formLevel={errors.formLevel} pending={write.isPending} onSubmit={submit} onClose={onClose}>
      <Field id="product-name" label={t('admin.org.form.name')} error={errors.fields.name}>
        <TextInput id="product-name" value={draft.name} onChange={(e) => set('name', e.target.value)} aria-invalid={errors.fields.name !== undefined} />
      </Field>
      <Field id="product-description" label={t('admin.org.products.description')} error={errors.fields.description}>
        <TextArea id="product-description" value={draft.description} onChange={(e) => set('description', e.target.value)} />
      </Field>
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field id="product-status" label={t('admin.org.products.statusLabel')} error={errors.fields.status}>
          <Select id="product-status" value={draft.status} onChange={(e) => set('status', STATUSES.find((s) => s === e.target.value) ?? 'live')}>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(STATUS_LABEL[status])}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="product-launchDate" label={t('admin.org.products.launchDate')} error={errors.fields.launchDate}>
          <TextInput id="product-launchDate" type="date" value={draft.launchDate} onChange={(e) => set('launchDate', e.target.value)} />
        </Field>
      </div>
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field id="product-orgUnitId" label={t('admin.org.products.entity')} error={errors.fields.orgUnitId}>
          <Select id="product-orgUnitId" value={draft.orgUnitId} onChange={(e) => set('orgUnitId', e.target.value)}>
            <option value="" disabled={product?.orgUnitId != null}>
              {t('admin.org.products.noEntity')}
            </option>
            {entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </Select>
        </Field>
        <PersonSelect id="product-ownerUserId" label={t('admin.org.products.owner')} error={errors.fields.ownerUserId} value={draft.ownerUserId} current={product?.owner ?? null} onChange={(id) => set('ownerUserId', id)} />
      </div>
      <TermPicker id="product-terms" label={t('admin.org.products.terms')} hint={t('admin.org.products.termsHint')} error={errors.fields.terms} groups={groups} value={draft.terms} onChange={(keys) => set('terms', keys)} />
    </DialogForm>
  );
}
