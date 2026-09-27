'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useId, useState, type ReactNode } from 'react';

import { accountLine, useInterfaceLanguages, useSignOutToPublicPage } from '@/components/shell/AccountMenu';
import { groupDestinations } from '@/components/shell/AppSidebar';
import { NavIcon } from '@/components/shell/NavIcon';
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { SidebarGroup, SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/components/ui/sidebar';
import { showsAccountLink, UnreadCount, useUnreadCount, withUnread } from '@/features/collab/NotificationBell';
import { useSession } from '@/features/identity/hooks';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { ACCOUNT_PARENT, childDestinations, isCurrent, moreDestinations, type Destination, type Surface } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';

// More, the last tab (design/system/navigation.md 3): a modal bottom sheet
// titled "More" with a Close button (touch screen-reader users cannot press
// Escape, and the scrim is hidden from them), every visible destination the
// bar does not hold, in the rail's groups, then a hairline and the account
// laid flat: name, organisation and roles, notifications with the unread
// count (NotificationBell.tsx), my passkeys, my sessions, the
// interface language as a radio group, sign out. Inside a sheet a second menu
// layer would add a tap for nothing.
//
// It carries no data-who-panel: that marker stays on the rail's row, which is
// still mounted below 1024 px, so Playwright finds exactly one.

export function MoreSheet({ surface, children }: { surface: Surface; children: ReactNode }) {
  const t = useT();
  const locale = useLocale();
  const pathname = usePathname();
  const permissions = usePermissions() ?? [];
  const { isCompact } = useSidebar();
  const { me } = useSession();
  const { pending, signOut } = useSignOutToPublicPage();
  const languages = useInterfaceLanguages();
  const languageName = useId();
  const unread = useUnreadCount();

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
    const bell = d.id === 'notifications';
    return (
      <SidebarMenuItem key={d.id}>
        <SidebarMenuButton asChild size="touch" isActive={current} tooltip={label}>
          {/* Closes even when the link is the current page, which navigates nowhere. */}
          <Link
            href={d.href}
            aria-current={current ? 'page' : undefined}
            aria-label={bell ? withUnread(label, unread, t) : undefined}
            onClick={() => setOpen(false)}
          >
            {icon ? <NavIcon id={d.id} /> : null}
            <span>{label}</span>
            {bell ? <UnreadCount count={unread} /> : null}
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  };

  const detail = me === null ? '' : accountLine(me, t);

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
                {childDestinations(ACCOUNT_PARENT, permissions)
                  .filter((d) => showsAccountLink(d.id, me))
                  .map((d) => row(d, false))}
              </SidebarMenu>
              {languages.options.length > 1 ? (
                // Stays open on a choice, so the sheet itself is seen to change language.
                <fieldset className="m-0 min-w-0 border-0 p-0">
                  <legend className="px-2 pt-1.5 pb-1 text-meta text-muted">{t('language.label')}</legend>
                  {languages.options.map((row) => (
                    <label
                      key={row.key}
                      lang={row.key}
                      className="flex min-h-11 cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-2 text-body hover:hover-fill has-[:disabled]:cursor-default has-[:disabled]:opacity-45"
                    >
                      {row.label}
                      <input
                        type="radio"
                        name={languageName}
                        value={row.key}
                        checked={row.key === locale}
                        disabled={languages.pending}
                        onChange={() => languages.choose(row.key)}
                        className="size-4 accent-fg"
                      />
                    </label>
                  ))}
                  {languages.failed ? (
                    <p role="alert" className="m-0 px-2 py-1.5 text-meta text-negative">
                      {t('language.failed')}
                    </p>
                  ) : null}
                </fieldset>
              ) : null}
              <SidebarMenu>
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
