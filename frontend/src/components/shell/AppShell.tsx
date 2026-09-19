'use client';

import type { ReactNode } from 'react';

import { Dock } from '@/components/shell/Dock';
import { MobileHeader } from '@/components/shell/MobileHeader';
import { Sidebar } from '@/components/shell/Sidebar';
import { useT } from '@/shared/i18n/LocaleProvider';
import type { Surface } from '@/shared/navigation/registry';

// Prototype `.app`: side rail plus main on desktop, header plus dock on
// phones. Main keeps the prototype's measure (1100px) and padding.
export function AppShell({ surface, children }: { surface: Surface; children: ReactNode }) {
  const t = useT();
  return (
    <div className="grid min-h-screen md:grid-cols-[240px_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-full focus:bg-surface focus:px-4 focus:py-2"
      >
        {t('shell.skipToContent')}
      </a>
      <Sidebar surface={surface} />
      <div className="min-w-0">
        <main id="main" tabIndex={-1} className="w-full max-w-[1100px] px-4 pt-5 pb-24 md:px-9 md:pt-8">
          <MobileHeader />
          {children}
        </main>
      </div>
      <Dock surface={surface} />
    </div>
  );
}
