'use client';

import { useTheme } from 'next-themes';

import { useT } from '@/shared/i18n/LocaleProvider';

// The public page's light and dark switch, in its footer. Which label shows is
// decided by CSS from the class next-themes sets on <html> before first paint,
// so the server render and the first client render agree and nothing flashes.
export function ThemeSwitch() {
  const t = useT();
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <button
      type="button"
      onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      className="microlabel inline-flex h-8 items-center rounded-control border border-line-control px-2.5 font-mono text-muted hover:text-fg hover:hover-fill"
    >
      <span className="dark:hidden">{t('public.theme.dark')}</span>
      <span className="hidden dark:inline">{t('public.theme.light')}</span>
    </button>
  );
}
