'use client';

import Link from 'next/link';

import { Logo } from '@/components/shell/Logo';
import { useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { homeOf, type Surface } from '@/shared/navigation/registry';

// The compact header, below 1024 px: the phonetic mark (64px, in the page's
// text colour) as a link to the person's home, Today or the console, at the
// top of the page and never sticky, so it scrolls away
// (design/system/navigation.md 12). The tab bar carries no brand, and the
// product is sold under its own wordmark (DECISIONS D-05). In the console the
// rail's kicker sits beside it, so nobody mistakes the surface. There is no
// menu button: the tab bar and its More sheet hold every destination.
export function MobileHeader({ surface }: { surface: Surface }) {
  const t = useT();
  const { me } = useSession();
  return (
    <header data-mobile-header="" className="mb-4 flex h-8 items-center gap-3 lg:hidden">
      <Link href={homeOf(me)} className="block text-fg">
        <Logo className="block h-auto w-[64px]" />
      </Link>
      {surface === 'console' ? <span className="microlabel text-muted">{t('shell.console')}</span> : null}
    </header>
  );
}
