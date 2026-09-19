'use client';

import type { ReactNode } from 'react';

import { AppSidebar } from '@/components/shell/AppSidebar';
import { MobileHeader } from '@/components/shell/MobileHeader';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { useT } from '@/shared/i18n/LocaleProvider';
import type { Surface } from '@/shared/navigation/registry';

// The shell on shadcn's Sidebar structure (ADR 0020 amendment 2026-09-19):
// SidebarProvider holds the open state (persisted, ctrl/cmd+b), the rail
// collapses to icons on desktop and becomes an off-canvas sheet on phones,
// and SidebarInset is the page. Main keeps the prototype's measure (1100px)
// and padding.
export function AppShell({ surface, children }: { surface: Surface; children: ReactNode }) {
  const t = useT();
  return (
    <SidebarProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2"
      >
        {t('shell.skipToContent')}
      </a>
      <AppSidebar surface={surface} />
      <SidebarInset id="main" tabIndex={-1} className="outline-none">
        <div className="w-full max-w-[1100px] px-4 pt-4 pb-16 md:px-9 md:pt-8">
          <MobileHeader />
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
