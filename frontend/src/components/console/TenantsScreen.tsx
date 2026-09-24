'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useConsoleTenants, useCreateConsoleTenant } from '@/features/console-tenants/hooks';
import { presentTenant } from '@/features/console-tenants/tenants-presentation';
import type { ConsoleTenant } from '@/features/console-tenants/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// Tenants (ADM-02, ADM-S6): every bank on the platform, and the one action
// that adds one and invites its first administrator in the same transaction.
// The screen reads the tenant rows only; nothing under a bank is asked for,
// so platform staff gain no way into a tenant's own data. The timezone, the
// default language and the content languages are the bank's own to set, on
// its Organisation profile screen, once its administrator is enrolled (D-68);
// this form asks for a name and that person's address, nothing else.

type FormProblem = 'name' | 'email';

function TenantRow({ tenant }: { tenant: ConsoleTenant }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-tenant-id={tenant.id} data-tenant-slug={tenant.slug}>
      <h3 className="mb-1 font-semibold">{tenant.name}</h3>
      <div className="mb-1.5">
        <PillRow pills={presentTenant(tenant, t)} />
      </div>
      <Meta>
        <span>{tenant.slug}</span>
        {tenant.defaultLanguage !== null ? <span>{tenant.defaultLanguage.label}</span> : null}
        <span>{t('console.tenants.created', { date: formatDate(tenant.createdAt, ctx) })}</span>
      </Meta>
    </Row>
  );
}

function CreateTenantModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (tenant: ConsoleTenant) => void;
}) {
  const t = useT();
  const create = useCreateConsoleTenant();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [title, setTitle] = useState('');
  const [problem, setProblem] = useState<FormProblem | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim() === '') {
      setProblem('name');
      return;
    }
    if (email.trim() === '') {
      setProblem('email');
      return;
    }
    setProblem(null);
    create.mutate(
      { name: name.trim(), firstAdminEmail: email.trim(), firstAdminTitle: title.trim() },
      {
        onSuccess: (tenant) => {
          onCreated(tenant);
          setName('');
          setEmail('');
          setTitle('');
          onClose();
        },
      },
    );
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={t('console.tenants.createTitle')} description={t('console.tenants.createBody')}>
      <form onSubmit={submit} noValidate aria-busy={create.isPending} data-tenant-form="">
        <Field id="tenant-name" label={t('console.tenants.name')} error={problem === 'name' ? t('console.tenants.nameRequired') : undefined}>
          <TextInput id="tenant-name" value={name} placeholder={t('console.tenants.namePlaceholder')} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field id="tenant-admin-email" label={t('console.tenants.adminEmail')} hint={t('console.tenants.adminEmailHint')} error={problem === 'email' ? t('console.tenants.adminEmailRequired') : undefined}>
          <TextInput id="tenant-admin-email" type="email" autoComplete="off" value={email} placeholder={t('console.tenants.adminEmailPlaceholder')} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field id="tenant-admin-title" label={t('console.tenants.adminTitle')}>
          <TextInput id="tenant-admin-title" value={title} placeholder={t('console.tenants.adminTitlePlaceholder')} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        {create.isError ? <ProblemAlert error={create.error} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={create.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('console.tenants.createAction')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function TenantsScreen() {
  const t = useT();
  const tenants = useConsoleTenants();
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<ConsoleTenant | null>(null);

  return (
    <>
      <PageHead
        title={t('console.tenants.title')}
        lede={t('console.tenants.lede')}
        actions={<Button onClick={() => setCreating(true)}>{t('console.tenants.create')}</Button>}
      />
      {created !== null ? <StatusLine tone="positive">{t('console.tenants.invited', { name: created.name })}</StatusLine> : null}
      {tenants.isPending ? (
        <LoadingState rows={3} />
      ) : tenants.isError ? (
        <ErrorState title={t('console.tenants.errorTitle')} onRetry={() => void tenants.refetch()} />
      ) : tenants.data.items.length === 0 ? (
        <EmptyState title={t('console.tenants.emptyTitle')} body={t('console.tenants.emptyBody')} />
      ) : (
        <Rows data-tenants-list="">
          {tenants.data.items.map((tenant) => (
            <TenantRow key={tenant.id} tenant={tenant} />
          ))}
        </Rows>
      )}
      <CreateTenantModal open={creating} onClose={() => setCreating(false)} onCreated={setCreated} />
    </>
  );
}
