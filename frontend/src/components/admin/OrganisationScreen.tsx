'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, Select, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useLanguages, useTenant, useUpdateTenant } from '@/features/tenant-admin/hooks';
import type { RoleRef, Tenant } from '@/features/tenant-admin/types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination } from '@/shared/navigation/registry';

// Organisation (design/screens/admin-organisation.html, TEN-01): name,
// timezone, default language, content languages in order, and the
// onboarding checklist the server computes. Any member may read; saving
// needs security.manage and the server's 403 renders in place.

const NORDIC_ZONES = ['Europe/Stockholm', 'Europe/Helsinki', 'Europe/Oslo', 'Europe/Copenhagen', 'Europe/Brussels'];

function stepLabel(key: string, t: Translate): string {
  switch (key) {
    case 'profile':
      return t('admin.organisation.step.profile');
    case 'members':
      return t('admin.organisation.step.members');
    case 'footprint':
      return t('admin.organisation.step.footprint');
    case 'vocabularies':
      return t('admin.organisation.step.vocabularies');
    case 'passkey':
      return t('admin.organisation.step.passkey');
    default:
      return key.replace(/_/g, ' ');
  }
}

function stepHref(key: string): string | null {
  switch (key) {
    case 'members':
      return findDestination('admin-members')?.href ?? null;
    case 'passkey':
      return findDestination('me-passkeys')?.href ?? null;
    case 'footprint':
      return findDestination('admin-footprint')?.href ?? null;
    case 'vocabularies':
      return findDestination('admin-vocabularies')?.href ?? null;
    default:
      return null;
  }
}

/** The languages to offer: the reference rows, or what the tenant already holds when the reference read failed. */
export function languageOptions(reference: RoleRef[] | undefined, tenant: Tenant): RoleRef[] {
  if (reference !== undefined && reference.length > 0) return reference;
  const known = new Map<string, RoleRef>();
  if (tenant.defaultLanguage !== null) known.set(tenant.defaultLanguage.key, tenant.defaultLanguage);
  for (const language of tenant.contentLanguages) known.set(language.key, language);
  return [...known.values()];
}

function ProfileForm({ tenant, languages }: { tenant: Tenant; languages: RoleRef[] }) {
  const t = useT();
  const update = useUpdateTenant();
  const [name, setName] = useState(tenant.name);
  const [timezone, setTimezone] = useState(tenant.timezone);
  const [defaultLanguage, setDefaultLanguage] = useState(tenant.defaultLanguage?.key ?? languages[0]?.key ?? '');
  const [content, setContent] = useState<string[]>(tenant.contentLanguages.map((l) => l.key));
  const [saved, setSaved] = useState(false);

  const toggle = (key: string, checked: boolean) => {
    setContent((current) => (checked ? [...current.filter((k) => k !== key), key] : current.filter((k) => k !== key)));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    update.mutate(
      { name: name.trim(), timezone: timezone.trim(), defaultLanguage: defaultLanguage || undefined, contentLanguages: content },
      { onSuccess: () => setSaved(true) },
    );
  };

  return (
    <form onSubmit={submit} noValidate aria-busy={update.isPending}>
      <Panel title={t('admin.organisation.profile')}>
        <Field id="org-name" label={t('admin.organisation.name')}>
          <TextInput id="org-name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="org-timezone" label={t('admin.organisation.timezone')} hint={t('admin.organisation.timezoneHint')}>
            <TextInput id="org-timezone" list="org-timezones" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
            <datalist id="org-timezones">
              {NORDIC_ZONES.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
          </Field>
          <Field id="org-default-language" label={t('admin.organisation.defaultLanguage')}>
            <Select id="org-default-language" value={defaultLanguage} onChange={(e) => setDefaultLanguage(e.target.value)}>
              {languages.map((language) => (
                <option key={language.key} value={language.key}>
                  {language.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <CheckGroup legend={t('admin.organisation.contentLanguages')} hint={t('admin.organisation.contentLanguagesHint')}>
          {languages.map((language) => (
            <CheckRow key={language.key} id={`org-lang-${language.key}`} label={language.label} checked={content.includes(language.key)} onChange={(checked) => toggle(language.key, checked)} />
          ))}
        </CheckGroup>
        {update.isError ? <ProblemAlert error={update.error} /> : null}
        {saved && !update.isPending ? <StatusLine tone="positive">{t('common.saved')}</StatusLine> : null}
        <ButtonBar>
          <Button type="submit" disabled={update.isPending}>
            {t('common.save')}
          </Button>
        </ButtonBar>
      </Panel>
    </form>
  );
}

function Checklist({ tenant }: { tenant: Tenant }) {
  const t = useT();
  const total = tenant.onboarding.steps.length;
  const done = tenant.onboarding.stepsDone;
  return (
    <Panel title={t('admin.organisation.checklist')} data-onboarding="">
      <div className="my-2 h-1.5 overflow-hidden rounded-[3px] bg-neutral-soft" aria-hidden="true">
        <i className="block h-full bg-accent" style={{ width: `${total === 0 ? 0 : Math.round((done / total) * 100)}%` }} />
      </div>
      <p className="text-meta text-muted">{t('admin.organisation.progress', { done, total })}</p>
      <ul className="m-0 list-none p-0">
        {tenant.onboarding.steps.map((step) => {
          const href = step.done ? null : stepHref(step.key);
          return (
            <li key={step.key} className="flex items-start gap-2.5 border-b border-line py-2.5 last:border-b-0" data-step={step.key} data-done={step.done ? '' : undefined}>
              <input type="checkbox" className="mt-0.5 h-5 w-5 accent-brand" checked={step.done} disabled readOnly aria-label={stepLabel(step.key, t)} />
              <span className={step.done ? 'text-muted line-through' : ''}>
                {stepLabel(step.key, t)}
                {href !== null ? (
                  <Link href={href} className="block text-meta">
                    {t('common.back').length > 0 ? stepLabel(step.key, t) : ''}
                  </Link>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export function OrganisationScreen() {
  const t = useT();
  const tenant = useTenant();
  const languages = useLanguages();

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.organisation.title')} lede={t('admin.organisation.lede')} />
      {tenant.isPending || languages.isPending ? (
        <LoadingState />
      ) : tenant.isError ? (
        <ErrorState title={t('admin.organisation.errorTitle')} onRetry={() => void tenant.refetch()} />
      ) : (
        <div className="grid items-start gap-4 md:grid-cols-[1.4fr_1fr]">
          {/* Keyed on the id: the form's own state is the draft, and a reseed elsewhere remounts it. */}
          <ProfileForm key={tenant.data.id} tenant={tenant.data} languages={languageOptions(languages.data, tenant.data)} />
          <Checklist tenant={tenant.data} />
        </div>
      )}
    </>
  );
}
