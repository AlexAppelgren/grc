'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Fragment } from 'react';

import { Logo } from '@/components/shell/Logo';
import { WhoPanel } from '@/components/shell/WhoPanel';
import { useT } from '@/shared/i18n/LocaleProvider';
import { isCurrent, visibleDestinations, type Destination, type NavGroup, type Surface } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';

const GROUP_ORDER: readonly NavGroup[] = ['primary', 'secondary', 'admin'];

function groupOf(destinations: readonly Destination[]): Destination[][] {
  return GROUP_ORDER.map((group) => destinations.filter((d) => d.group === group)).filter((g) => g.length > 0);
}

// The dark green side rail from the prototype (`.side`): 240px, sticky,
// the wordmark on top, the registry's destinations, then the who panel.
export function Sidebar({ surface }: { surface: Surface }) {
  const t = useT();
  const pathname = usePathname();
  const permissions = usePermissions();
  const groups = groupOf(visibleDestinations(surface, permissions ?? []));

  return (
    <aside className="sticky top-0 hidden h-screen overflow-auto bg-brand px-3.5 py-6 text-on-brand md:block">
      <div className="px-2 pb-5">
        <Logo className="block h-auto w-full max-w-[196px]" />
      </div>
      <nav aria-label={t('nav.main')}>
        {groups.map((group, i) => (
          <Fragment key={group[0]?.id ?? i}>
            {i > 0 ? <hr className="mx-2 my-3 border-0 border-t border-on-brand-line" /> : null}
            {group.map((d) => {
              const current = isCurrent(d, pathname);
              return (
                <Link
                  key={d.id}
                  href={d.href}
                  aria-current={current ? 'page' : undefined}
                  className={cn(
                    'flex w-full items-center justify-between rounded-full px-3 py-2.5 text-left no-underline',
                    current ? 'bg-rail-current font-semibold text-on-rail-current' : 'hover:bg-on-brand-hover',
                  )}
                >
                  {t(d.labelKey)}
                </Link>
              );
            })}
          </Fragment>
        ))}
      </nav>
      <WhoPanel />
    </aside>
  );
}
