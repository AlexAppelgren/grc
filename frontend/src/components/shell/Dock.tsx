'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { NavIcon } from '@/components/shell/NavIcon';
import { useT } from '@/shared/i18n/LocaleProvider';
import { dockDestinations, isCurrent, type Surface } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';

// Prototype `.tabbar`: the phone dock, fixed at the bottom, derived from the
// registry's dock ranks. Empty when nothing is unlocked.
export function Dock({ surface }: { surface: Surface }) {
  const t = useT();
  const pathname = usePathname();
  const permissions = usePermissions();
  const items = dockDestinations(surface, permissions ?? []);
  if (items.length === 0) return null;

  return (
    <nav
      aria-label={t('nav.main')}
      className="fixed inset-x-0 bottom-0 z-30 grid bg-brand pb-[env(safe-area-inset-bottom)] md:hidden"
      style={{ gridTemplateColumns: `repeat(${items.length}, 1fr)` }}
    >
      {items.map((d) => {
        const current = isCurrent(d, pathname);
        return (
          <Link
            key={d.id}
            href={d.href}
            aria-current={current ? 'page' : undefined}
            className={cn(
              'grid justify-items-center gap-0.5 px-0.5 pt-2.5 pb-2 text-meta no-underline',
              current ? 'font-semibold text-on-brand' : 'text-on-brand-muted',
            )}
          >
            <NavIcon id={d.id} />
            {t(d.labelKey)}
          </Link>
        );
      })}
    </nav>
  );
}
