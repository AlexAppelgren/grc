'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { AccountMenu } from '@/components/shell/AccountMenu';
import { Logo, LogoMark } from '@/components/shell/Logo';
import { NavIcon } from '@/components/shell/NavIcon';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar';
import { useT } from '@/shared/i18n/LocaleProvider';
import { isCurrent, visibleDestinations, type Destination, type NavGroup, type Surface } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';

const GROUP_ORDER: readonly NavGroup[] = ['primary', 'secondary', 'admin'];

export function groupDestinations(destinations: readonly Destination[]): Destination[][] {
  return GROUP_ORDER.map((group) => destinations.filter((d) => d.group === group)).filter((g) => g.length > 0);
}

// The rail from 1024 px (ADR 0020 amendment 2026-09-19; below that width the
// tab bar and the More sheet, design/system/navigation.md): shadcn's Sidebar structure in
// seb.io's restraint. The phonetic mark alone on top as a small signature
// (about 68px, currentColor, foundations.md), the open e alone when collapsed; the registry's
// destinations in its groups, separated by space rather than headings; the
// signed-in person and "Minimise menu" pinned at the bottom. It renders
// whatever the registry holds for this surface and permission list, so a
// destination added there appears here with no change to this file.
export function AppSidebar({ surface }: { surface: Surface }) {
  const t = useT();
  const pathname = usePathname();
  const permissions = usePermissions();
  const { state, toggleSidebar } = useSidebar();
  const groups = groupDestinations(visibleDestinations(surface, permissions ?? []));
  const collapsed = state === 'collapsed';

  return (
    <Sidebar>
      <SidebarHeader className="px-4 pt-5 pb-3 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:px-0">
        <Link href="/" className="block text-sidebar-foreground">
          <Logo className="block h-auto w-[68px] group-data-[collapsible=icon]:hidden" />
          <LogoMark className="hidden size-5 group-data-[collapsible=icon]:block" />
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <nav aria-label={t('nav.main')}>
          {groups.map((group) => (
            <SidebarGroup key={group[0]?.group} data-nav-group={group[0]?.group} className="py-2">
              <SidebarMenu>
                {group.map((d) => {
                  const label = t(d.labelKey);
                  const current = isCurrent(d, pathname);
                  return (
                    <SidebarMenuItem key={d.id}>
                      <SidebarMenuButton asChild isActive={current} tooltip={label}>
                        <Link href={d.href} aria-current={current ? 'page' : undefined}>
                          <NavIcon id={d.id} />
                          <span>{label}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>

      {/* The footer clears the iPad home indicator in landscape (design/system/navigation.md 7). */}
      <SidebarFooter className="pb-[max(1rem,env(safe-area-inset-bottom))]">
        <AccountMenu />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="sm"
              data-sidebar-minimise=""
              tooltip={t('sidebar.expand')}
              aria-label={collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
              aria-expanded={!collapsed}
              onClick={toggleSidebar}
              className="text-sidebar-muted-foreground"
            >
              <NavIcon id={collapsed ? 'sidebar-expand' : 'sidebar-collapse'} />
              <span>{collapsed ? t('sidebar.expand') : t('sidebar.collapse')}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
