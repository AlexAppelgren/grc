'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, type ReactNode } from 'react';

import { secondLine, useSignOutToSignIn } from '@/components/shell/AccountMenu';
import { groupDestinations } from '@/components/shell/AppSidebar';
import { NavIcon } from '@/components/shell/NavIcon';
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { SidebarGroup, SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/components/ui/sidebar';
import { useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { ACCOUNT_PARENT, childDestinations, isCurrent, moreDestinations, type Destination, type Surface } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';

// More, the last tab (design/system/navigation.md 3): a modal bottom sheet
// titled "More" with a Close button (touch screen-reader users cannot press
// Escape, and the scrim is hidden from them), every visible destination the
// bar does not hold, in the rail's groups, then a hairline and the account
// laid flat: name, organisation and roles, my passkeys, my sessions, sign
// out. Inside a sheet a second menu layer would add a tap for nothing.
//
// It carries no data-who-panel: that marker stays on the rail's row, which is
// still mounted below 1024 px, so Playwright finds exactly one.

export function MoreSheet({ surface, children }: { surface: Surface; children: ReactNode }) {
  const t = useT();
  const pathname = usePathname();
  const permissions = usePermissions() ?? [];
  const { isCompact } = useSidebar();
  const { me } = useSession();
  const { pending, signOut } = useSignOutToSignIn();

  // Any route change closes the sheet (the Android back gesture, Safari's edge
  // swipe: Next keeps layout state across history navigation), and so does
  // crossing 1024 px (a rotated iPad), where More is hidden. Reset during
  // render, React's pattern for state that follows a value; an effect would be
  // react-hooks/set-state-in-effect.
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState({ pathname, isCompact });
  if (seen.pathname !== pathname || seen.isCompact !== isCompact) {
    setSeen({ pathname, isCompact });
    setOpen(false);
  }

  const row = (d: Destination, icon: boolean) => {
    const current = isCurrent(d, pathname);
    const label = t(d.labelKey);
    return (
      <SidebarMenuItem key={d.id}>
        <SidebarMenuButton asChild size="touch" isActive={current} tooltip={label}>
          {/* Closes even when the link is the current page, which navigates nowhere. */}
          <Link href={d.href} aria-current={current ? 'page' : undefined} onClick={() => setOpen(false)}>
            {icon ? <NavIcon id={d.id} /> : null}
            <span>{label}</span>
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  };

  const roles = me?.roles.map((role) => role.label).join(', ') ?? '';
  const detail = secondLine(me?.tenant?.name ?? null, roles, t);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>{children}</SheetTrigger>
      <SheetContent
        onCloseAutoFocus={(event) => {
          // Closed by crossing to 1024 px or wider: More is hidden, so focus the page.
          if (!isCompact) {
            event.preventDefault();
            document.getElementById('main')?.focus();
          }
        }}
      >
        <div className="flex items-center justify-between gap-2 py-1 pr-2 pl-4">
          <SheetTitle>{t('nav.more')}</SheetTitle>
          <SheetClose aria-label={t('shell.close')} className="inline-flex size-11 items-center justify-center rounded-control text-fg hover:hover-fill">
            <NavIcon id="close" size="tab" />
          </SheetClose>
        </div>
        <div className="min-h-0 overflow-y-auto">
          {groupDestinations(moreDestinations(surface, permissions)).map((group) => (
            <SidebarGroup key={group[0]?.group} data-nav-group={group[0]?.group}>
              <SidebarMenu>{group.map((d) => row(d, true))}</SidebarMenu>
            </SidebarGroup>
          ))}
          {me === null ? null : (
            <div role="group" aria-label={t('shell.account')} className="mx-2 mt-1.5 border-t border-line pt-3">
              <div className="mb-2 px-2">
                <p className="font-medium">{me.user.name}</p>
                {detail.length > 0 ? <p className="text-meta text-muted">{detail}</p> : null}
              </div>
              <SidebarMenu>
                {childDestinations(ACCOUNT_PARENT, permissions).map((d) => row(d, false))}
                <SidebarMenuItem>
                  <SidebarMenuButton size="touch" tooltip={t('shell.signOut')} disabled={pending} onClick={signOut} className="disabled:opacity-45">
                    <span>{pending ? t('shell.signingOut') : t('shell.signOut')}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
