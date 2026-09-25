'use client';

import type { ReactNode } from 'react';

import { AppSidebar } from '@/components/shell/AppSidebar';
import { MobileHeader } from '@/components/shell/MobileHeader';
import { TabBar } from '@/components/shell/TabBar';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { surfaceOf, type Surface } from '@/shared/navigation/registry';

// The shell on shadcn's Sidebar structure (ADR 0020 amendment 2026-09-19):
// SidebarProvider holds the open state (persisted, ctrl/cmd+b), the rail
// collapses to icons from 1024 px, the floating tab bar and its More sheet
// take over below it (design/system/navigation.md), and SidebarInset is the
// page. The DOM order is skip link, rail, bar, main, so navigation comes
// before content at every width. Main takes foundations.md's measure: 1200px,
// left aligned beside the rail, 24 / 32px padding (12 / 16px on phones), every
// side at least its safe-area inset (notched phones in landscape are past the
// 768px step), and the bottom clear of the bar below 1024 px.
export function AppShell({ surface, children }: { surface: Surface; children: ReactNode }) {
  const t = useT();
  return (
    <SidebarProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-[max(8px,env(safe-area-inset-top))] focus:left-[max(8px,env(safe-area-inset-left))] focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2"
      >
        {t('shell.skipToContent')}
      </a>
      <AppSidebar surface={surface} />
      <TabBar surface={surface} />
      <SidebarInset id="main" tabIndex={-1} className="outline-none">
        <div className="w-full max-w-[1200px] pt-[max(12px,env(safe-area-inset-top))] pr-[max(1rem,env(safe-area-inset-right))] pl-[max(1rem,env(safe-area-inset-left))] max-lg:pb-[calc(var(--tabbar-top)+16px)] md:pt-6 md:pr-[max(2rem,env(safe-area-inset-right))] md:pl-[max(2rem,env(safe-area-inset-left))] lg:pb-16">
          <MobileHeader surface={surface} />
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

/**
 * The shell of the signed-in person's own surface, for the pages every
 * signed-in person shares (the tenant group: /me, not-found): platform staff,
 * who have no tenant, keep the console rail there.
 */
export function PrincipalShell({ children }: { children: ReactNode }) {
  const { me } = useSession();
  return <AppShell surface={surfaceOf(me)}>{children}</AppShell>;
}
