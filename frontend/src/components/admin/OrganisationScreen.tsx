'use client';

import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { OnboardingChecklist } from '@/components/admin/OnboardingChecklist';
import { DepartmentsSection } from '@/components/admin/DepartmentsSection';
import { EntitiesSection } from '@/components/admin/EntitiesSection';
import { ProductsSection } from '@/components/admin/ProductsSection';
import { TeamsSection } from '@/components/admin/TeamsSection';
import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, Select, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useLanguages, useSetTenantAi, useTenant, useUpdateTenant } from '@/features/tenant-admin/hooks';
import type { RoleRef, Tenant } from '@/features/tenant-admin/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// Organisation (design/screens/admin-organisation.html, TEN-01): name,
// timezone, default language, content languages in order, and the
// onboarding checklist the server computes. Any member may read; saving
// needs security.manage and the server's 403 renders in place. The switch over
// this organisation's Ask and AI drafts (D-07) is its own security change: the
// api client opens the passkey prompt on the server's step_up_required.
// Below them, one mount point per section of the organisation (TEN-02): each
// section reads and writes on its own, under vocab.manage.

// One zone per home market's capital (D-145), and Brussels. A suggestion only: the field takes any IANA name.
const SUGGESTED_ZONES = [
  'Europe/Stockholm',
  'Europe/Copenhagen',
  'Europe/Oslo',
  'Europe/Helsinki',
  'Europe/Tallinn',
  'Europe/Riga',
  'Europe/Vilnius',
  'Europe/Berlin',
  'Europe/London',
  'Europe/Amsterdam',
  'Europe/Vienna',
  'Europe/Zurich',
  'Europe/Brussels',
];


/** The languages to offer: the reference rows, or what the tenant already holds when the reference read failed. */
export function languageOptions(reference: RoleRef[] | undefined, tenant: Tenant): RoleRef[] {
  if (reference !== undefined && reference.length > 0) return reference;
  const known = new Map<string, RoleRef>();
  if (tenant.defaultLanguage !== null) known.set(tenant.defaultLanguage.key, tenant.defaultLanguage);
  for (const language of tenant.contentLanguages) known.set(language.key, language);
  return [...known.values()];
}

const sameOrder = (a: string[], b: string[]) => a.length === b.length && a.every((key, i) => key === b[i]);

function ProfileForm({ tenant, languages }: { tenant: Tenant; languages: RoleRef[] }) {
  const t = useT();
  const update = useUpdateTenant();
  const held = tenant.contentLanguages.map((l) => l.key);
  const [name, setName] = useState(tenant.name);
  const [timezone, setTimezone] = useState(tenant.timezone);
  // A tenant created from the console has no default language yet (D-68): the select
  // starts on its placeholder rather than on whichever language happens to come first.
  const [defaultLanguage, setDefaultLanguage] = useState(tenant.defaultLanguage?.key ?? '');
  const [content, setContent] = useState<string[]>(held);
  const [languagesMissing, setLanguagesMissing] = useState(false);
  const [saved, setSaved] = useState(false);

  const toggle = (key: string, checked: boolean) => {
    setLanguagesMissing(false);
    setContent((current) => (checked ? [...current.filter((k) => k !== key), key] : current.filter((k) => k !== key)));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    // The server refuses an empty list; a tenant that keeps content languages cannot be left with none.
    if (content.length === 0 && held.length > 0) {
      setLanguagesMissing(true);
      return;
    }
    // An omitted field is left alone: the languages go only when the draft changed them,
    // and the default language only once one has been chosen.
    update.mutate(
      { name: name.trim(), timezone: timezone.trim(), defaultLanguage: defaultLanguage || undefined, contentLanguages: sameOrder(content, held) ? undefined : content },
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
              {SUGGESTED_ZONES.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
          </Field>
          <Field id="org-default-language" label={t('admin.organisation.defaultLanguage')}>
            <Select id="org-default-language" value={defaultLanguage} onChange={(e) => setDefaultLanguage(e.target.value)}>
              <option value="" disabled>
                {t('admin.organisation.defaultLanguagePlaceholder')}
              </option>
              {languages.map((language) => (
                <option key={language.key} value={language.key}>
                  {language.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <CheckGroup legend={t('admin.organisation.contentLanguages')} hint={t('admin.organisation.contentLanguagesHint')} error={languagesMissing ? t('admin.organisation.contentLanguagesRequired') : undefined}>
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

function AiSwitch({ tenant }: { tenant: Tenant }) {
  const t = useT();
  const toggle = useSetTenantAi();
  const on = tenant.aiEnabled;
  return (
    <Panel title={t('admin.organisation.ai.title')} aria-busy={toggle.isPending}>
      <p>{on ? t('admin.organisation.ai.on', { name: tenant.name }) : t('admin.organisation.ai.off', { name: tenant.name })}</p>
      <p className="text-meta text-muted">{t('admin.organisation.ai.hint')}</p>
      {toggle.isError ? <ProblemAlert error={toggle.error} codes={{ step_up_required: t('admin.organisation.ai.stepUpCancelled') }} /> : null}
      <ButtonBar>
        <Button variant={on ? 'outline' : 'primary'} disabled={toggle.isPending} onClick={() => toggle.mutate(!on)}>
          {toggle.isPending ? t('admin.organisation.ai.switching') : on ? t('admin.organisation.ai.switchOff') : t('admin.organisation.ai.switchOn')}
        </Button>
      </ButtonBar>
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
          <div>
            <ProfileForm key={tenant.data.id} tenant={tenant.data} languages={languageOptions(languages.data, tenant.data)} />
            <AiSwitch tenant={tenant.data} />
          </div>
          <OnboardingChecklist tenant={tenant.data} />
        </div>
      )}
      <DepartmentsSection />
      <TeamsSection />
      <EntitiesSection />
      <ProductsSection />
    </>
  );
}
