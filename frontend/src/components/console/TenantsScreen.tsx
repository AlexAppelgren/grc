'use client';

import type { UseQueryResult } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, Select, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useConsoleTenants, useCreateConsoleTenant } from '@/features/console-tenants/hooks';
import { presentTenant } from '@/features/console-tenants/tenants-presentation';
import type { ConsoleTenant, LanguageRef } from '@/features/console-tenants/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useLanguages } from '@/features/tenant-admin/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// Tenants (ADM-02, ADM-S6): every bank on the platform, and the one action
// that adds one and invites its first administrator in the same transaction.
// The screen reads the tenant rows only; nothing under a bank is asked for,
// so platform staff gain no way into a tenant's own data. The timezones and
// the languages are the same reference reads the organisation profile makes.

const NORDIC_ZONES = ['Europe/Stockholm', 'Europe/Helsinki', 'Europe/Oslo', 'Europe/Copenhagen', 'Europe/Brussels'];
const DEFAULT_ZONE = 'Europe/Stockholm';

type FormProblem = 'name' | 'slug' | 'email' | 'languages';

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

// `languages` is the reference read GET /reference/languages, the same rows
// the organisation profile offers; it is a capability read for any session, so
// the console makes it without holding anything of a tenant's.
function CreateTenantModal({
  open,
  onClose,
  onCreated,
  languages,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (tenant: ConsoleTenant) => void;
  languages: UseQueryResult<LanguageRef[]>;
}) {
  const t = useT();
  const create = useCreateConsoleTenant();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [timezone, setTimezone] = useState(DEFAULT_ZONE);
  const [defaultLanguage, setDefaultLanguage] = useState('');
  const [content, setContent] = useState<string[] | null>(null);
  const [email, setEmail] = useState('');
  const [title, setTitle] = useState('');
  const [problem, setProblem] = useState<FormProblem | null>(null);

  // The reference read decides the options, so the first row is the default
  // until the person chooses another; `null` content means the person has not
  // touched the list yet, and the default language stands in for it.
  const options = languages.data ?? [];
  const chosenLanguage = defaultLanguage === '' ? (options[0]?.key ?? '') : defaultLanguage;
  const contentKeys = content ?? (chosenLanguage === '' ? [] : [chosenLanguage]);

  const toggle = (key: string, checked: boolean) => {
    setContent(checked ? [...contentKeys.filter((k) => k !== key), key] : contentKeys.filter((k) => k !== key));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim() === '') {
      setProblem('name');
      return;
    }
    if (slug.trim() === '') {
      setProblem('slug');
      return;
    }
    if (email.trim() === '') {
      setProblem('email');
      return;
    }
    if (contentKeys.length === 0) {
      setProblem('languages');
      return;
    }
    setProblem(null);
    create.mutate(
      {
        name: name.trim(),
        slug: slug.trim(),
        timezone: timezone.trim(),
        defaultLanguage: chosenLanguage,
        contentLanguages: contentKeys,
        firstAdminEmail: email.trim(),
        firstAdminTitle: title.trim(),
      },
      {
        onSuccess: (tenant) => {
          onCreated(tenant);
          setName('');
          setSlug('');
          setEmail('');
          setTitle('');
          setContent(null);
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
        <Field id="tenant-slug" label={t('console.tenants.slug')} hint={t('console.tenants.slugHint')} error={problem === 'slug' ? t('console.tenants.slugRequired') : undefined}>
          <TextInput id="tenant-slug" value={slug} placeholder={t('console.tenants.slugPlaceholder')} onChange={(e) => setSlug(e.target.value)} />
        </Field>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="tenant-timezone" label={t('console.tenants.timezone')} hint={t('console.tenants.timezoneHint')}>
            <TextInput id="tenant-timezone" list="tenant-timezones" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
            <datalist id="tenant-timezones">
              {NORDIC_ZONES.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
          </Field>
          <Field id="tenant-default-language" label={t('console.tenants.defaultLanguage')}>
            <Select id="tenant-default-language" value={chosenLanguage} onChange={(e) => setDefaultLanguage(e.target.value)}>
              {options.map((language) => (
                <option key={language.key} value={language.key}>
                  {language.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <CheckGroup
          legend={t('console.tenants.contentLanguages')}
          hint={t('console.tenants.contentLanguagesHint')}
          error={problem === 'languages' ? t('console.tenants.languagesRequired') : undefined}
        >
          {languages.isPending ? <StatusLine>{t('common.loading')}</StatusLine> : null}
          {languages.isError ? <ProblemAlert error={languages.error} /> : null}
          {options.map((language) => (
            <CheckRow
              key={language.key}
              id={`tenant-lang-${language.key}`}
              label={language.label}
              checked={contentKeys.includes(language.key)}
              onChange={(checked) => toggle(language.key, checked)}
            />
          ))}
        </CheckGroup>
        <Field id="tenant-admin-email" label={t('console.tenants.adminEmail')} hint={t('console.tenants.adminEmailHint')} error={problem === 'email' ? t('console.tenants.adminEmailRequired') : undefined}>
          <TextInput id="tenant-admin-email" type="email" autoComplete="off" value={email} placeholder={t('console.tenants.adminEmailPlaceholder')} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field id="tenant-admin-title" label={t('console.tenants.adminTitle')}>
          <TextInput id="tenant-admin-title" value={title} placeholder={t('console.tenants.adminTitlePlaceholder')} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        {create.isError ? <ProblemAlert error={create.error} codes={{ duplicate_key: t('console.tenants.slugTaken') }} /> : null}
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
  const languages = useLanguages();
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
      <CreateTenantModal open={creating} onClose={() => setCreating(false)} onCreated={setCreated} languages={languages} />
    </>
  );
}
