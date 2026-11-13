'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { useDemoFrame } from '@/features/demo/frame';
import { useT } from '@/shared/i18n/LocaleProvider';
import { adminGroups, currentAdminPage } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';

// Admin's tab bar (D-137, design/system/navigation.md "Admin"): the groups this
// person's permissions unlock, then the pages of the group they are in. A group
// tab opens its first page. Nothing here checks a role name. The public page's
// demo shows none: its recordings hold no page of Admin a tab would open.
export function AdminTabs() {
  const t = useT();
  const pathname = usePathname() ?? '';
  const groups = adminGroups(usePermissions() ?? []);
  const demo = useDemoFrame();
  if (demo || groups.length === 0) return null;
  const current = currentAdminPage(
    groups.flatMap((g) => g.pages),
    pathname,
  );
  const group = groups.find((g) => current !== undefined && g.pages.includes(current));
  return (
    <div className="mb-6">
      <p className="microlabel mb-2 text-muted">{t('admin.title')}</p>
      <nav aria-label={t('admin.sections')} className="-mx-1 flex gap-1 overflow-x-auto border-b border-line px-1">
        {groups.map((g) => (
          <Link
            key={g.id}
            href={g.pages[0]?.href ?? '/admin'}
            aria-current={g === group ? 'page' : undefined}
            data-admin-group={g.id}
            data-admin-sections={g.pages.map((d) => d.id).join(' ')}
            className={cn('-mb-px border-b-2 px-2.5 py-2 font-medium whitespace-nowrap no-underline', g === group ? 'border-fg text-fg' : 'border-transparent text-muted hover:text-fg')}
          >
            {t(g.labelKey)}
          </Link>
        ))}
      </nav>
      {group !== undefined ? (
        <nav aria-label={t('admin.pages')} className="mt-3 flex flex-wrap gap-2">
          {group.pages.map((d) => (
            <Link
              key={d.id}
              href={d.href}
              aria-current={d === current ? 'page' : undefined}
              data-admin-section={d.id}
              className={cn(
                'inline-flex h-8 items-center rounded-control border px-3 text-body font-medium whitespace-nowrap no-underline',
                d === current ? 'border-line-strong bg-neutral-soft text-fg' : 'border-transparent text-muted hover:text-fg',
              )}
            >
              {t(d.labelKey)}
            </Link>
          ))}
        </nav>
      ) : null}
    </div>
  );
}
