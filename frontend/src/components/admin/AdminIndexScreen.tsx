'use client';

import Link from 'next/link';

import { PageHead } from '@/components/ui/PageHead';
import { Rows } from '@/components/ui/Panel';
import { useT } from '@/shared/i18n/LocaleProvider';
import { childDestinations } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';

// /admin: the sections this person's permissions unlock, from the registry
// (ADM-01, ADM-03). Nothing here checks a role name.
export function AdminIndexScreen() {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const sections = childDestinations('admin', permissions);
  return (
    <>
      <PageHead title={t('admin.title')} lede={t('admin.lede')} />
      <Rows>
        {sections.map((d) => (
          <Link key={d.id} href={d.href} className="block rounded-m border border-line bg-surface px-4.5 py-4 font-semibold no-underline hover:border-fg" data-admin-section={d.id}>
            {t(d.labelKey)}
          </Link>
        ))}
      </Rows>
    </>
  );
}
