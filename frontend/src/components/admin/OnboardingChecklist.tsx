'use client';

import Link from 'next/link';

import { Panel } from '@/components/ui/Panel';
import type { Tenant } from '@/features/tenant-admin/types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination } from '@/shared/navigation/registry';
import { humaniseKey } from '@/shared/utils/format';

// "Getting started" (TEN-01): the onboarding checklist the server computes, on the
// Organisation screen and on Today for whoever can work through it. An open step's title
// is the link to the screen that completes it; a done one is struck through.

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
      return humaniseKey(key);
  }
}

function stepHref(key: string): string | null {
  switch (key) {
    case 'profile':
      return findDestination('admin-organisation')?.href ?? null;
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

export function OnboardingChecklist({ tenant }: { tenant: Tenant }) {
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
          const label = stepLabel(step.key, t);
          return (
            <li key={step.key} className="flex items-start gap-2.5 border-b border-line py-2.5 last:border-b-0" data-step={step.key} data-done={step.done ? '' : undefined}>
              <input type="checkbox" className="mt-0.5 h-5 w-5 accent-brand" checked={step.done} disabled readOnly aria-label={label} />
              {step.done ? (
                <span className="text-muted line-through">{label}</span>
              ) : href === null ? (
                <span>{label}</span>
              ) : (
                <Link href={href} className="underline">
                  {label}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
