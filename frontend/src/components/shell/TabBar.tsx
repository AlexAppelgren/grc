'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef } from 'react';

import { MoreSheet } from '@/components/shell/MoreSheet';
import { NavIcon } from '@/components/shell/NavIcon';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { dockDestinations, isCurrent, isInMore, type Surface } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';

// The floating tab bar below 1024 px (design/system/navigation.md, Alex
// 2026-09-19): the registry's dock destinations, lowest rank first, then More,
// which opens the rest and the account. A plain list of links in a "Main" nav,
// never a tablist or a menu. CSS alone shows it (`lg:hidden`), so it renders
// on the server and nothing flashes; globals.css holds the short-viewport and
// on-screen-keyboard rules and the page clearance it measures for.

// Each cell is the whole hit area, 52px tall. The current tab takes the
// rail's accent over the cell plus a 1px line-strong outline inset by 1px,
// the indicator that reaches 3:1 (fill alone is 1.19:1); keyboard focus
// replaces the outline with the focus ring.
const CELL = [
  'flex min-h-13 flex-col items-center justify-center gap-1 rounded-control text-meta text-muted no-underline transition-colors',
  'hover:hover-fill',
  'data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground',
  'data-[active=true]:not-focus-visible:outline data-[active=true]:not-focus-visible:-outline-offset-1 data-[active=true]:not-focus-visible:outline-line-strong',
].join(' ');

// One or two lines, never truncated or shrunk: a long word hyphenates where
// the browser has a dictionary for the nav's lang, and breaks anywhere
// otherwise.
const LABEL = 'max-w-full text-center hyphens-auto wrap-anywhere';

export function TabBar({ surface }: { surface: Surface }) {
  const t = useT();
  const locale = useLocale();
  const pathname = usePathname();
  const permissions = usePermissions() ?? [];
  const inMore = isInMore(surface, permissions, pathname);
  const bar = useRef<HTMLElement>(null);

  // The page and scroll padding clear the bar by its real height: a wrapped
  // label or text-only zoom makes it taller than 64px. A 0 height (the bar
  // hidden from 1024 px) is ignored, so the last value stands.
  useEffect(() => {
    const root = document.documentElement;
    const observer = new ResizeObserver(([entry]) => {
      const height = entry?.borderBoxSize[0]?.blockSize ?? 0;
      if (height > 0) root.style.setProperty('--tabbar-height', `${height}px`);
    });
    if (bar.current !== null) observer.observe(bar.current);
    return () => {
      observer.disconnect();
      root.style.removeProperty('--tabbar-height');
    };
  }, []);

  return (
    <nav
      ref={bar}
      aria-label={t('nav.main')}
      lang={locale}
      data-slot="tab-bar"
      className={[
        'fixed right-[max(16px,env(safe-area-inset-right))] bottom-(--tabbar-bottom) left-[max(16px,env(safe-area-inset-left))] z-30 mx-auto w-fit',
        'max-[25rem]:right-[max(8px,env(safe-area-inset-right))] max-[25rem]:left-[max(8px,env(safe-area-inset-left))]',
        'rounded-overlay border border-line bg-surface p-1.5 shadow-float lg:hidden print:hidden',
      ].join(' ')}
    >
      <ul className="grid auto-cols-[minmax(0,6rem)] grid-flow-col">
        {dockDestinations(surface, permissions).map((d) => {
          const current = isCurrent(d, pathname);
          return (
            <li key={d.id} className="grid">
              <Link href={d.href} aria-current={current ? 'page' : undefined} data-active={current} className={CELL}>
                <NavIcon id={d.id} size="tab" />
                <span className={LABEL}>{t(d.shortLabelKey ?? d.labelKey)}</span>
              </Link>
            </li>
          );
        })}
        <li className="grid">
          <MoreSheet surface={surface}>
            {/* "true", not "page": More is not a link to the page, it holds it (navigation.md 11). */}
            <button type="button" data-active={inMore} aria-current={inMore ? 'true' : undefined} className={CELL}>
              <NavIcon id="more" size="tab" />
              <span className={LABEL}>{t('nav.more')}</span>
            </button>
          </MoreSheet>
        </li>
      </ul>
    </nav>
  );
}
