'use client';

import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { NavIcon } from '@/components/shell/NavIcon';
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/components/ui/sidebar';
import { useSession, useSignOut } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { ACCOUNT_PARENT, childDestinations } from '@/shared/navigation/registry';

// The signed-in person as one quiet row in the rail's footer: name, then
// organisation and roles, and a menu for my passkeys, my sessions and sign
// out. No avatar, no bordered card (the "who" panel it replaces). The
// prototype's "Switch user" never ships (design/README.md).
//
// `data-who-panel` stays on the row's wrapper because the E2E journeys locate
// the signed-in person by it. The menu renders without a portal, so its items
// are descendants of that wrapper while it is open.

const MENU_ITEM =
  'flex w-full cursor-pointer items-center rounded-md px-2 py-1.5 text-body text-sidebar-foreground no-underline outline-hidden data-[highlighted]:bg-sidebar-accent disabled:opacity-45';

export function secondLine(organisation: string | null, roles: string, t: ReturnType<typeof useT>): string {
  if (organisation !== null && roles.length > 0) return t('shell.orgRoles', { organisation, roles });
  return organisation ?? roles;
}

export function AccountMenu() {
  const t = useT();
  const router = useRouter();
  const { me } = useSession();
  const { isMobile, setOpenMobile } = useSidebar();
  const signOut = useSignOut();

  // The session gate renders the shell only for a signed-in person.
  if (me === null) return null;

  const roles = me.roles.map((role) => role.label).join(', ');
  const detail = secondLine(me.tenant?.name ?? null, roles, t);
  const links = childDestinations(ACCOUNT_PARENT, me.permissions);

  return (
    <SidebarMenu data-who-panel="">
      <SidebarMenuItem>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <SidebarMenuButton size="lg" tooltip={me.user.name} aria-label={t('shell.accountFor', { name: me.user.name })}>
              <NavIcon id="account" />
              <span className="grid min-w-0 flex-1 leading-tight">
                <span className="truncate">{me.user.name}</span>
                {detail.length > 0 ? <span className="truncate text-meta text-sidebar-muted-foreground">{detail}</span> : null}
              </span>
            </SidebarMenuButton>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content
            side={isMobile ? 'top' : 'right'}
            align="end"
            sideOffset={8}
            className="z-50 min-w-56 rounded-md border border-sidebar-border bg-sidebar p-1 text-sidebar-foreground"
          >
            <DropdownMenu.Label className="px-2 py-1.5 text-meta text-sidebar-muted-foreground">
              {t('shell.signedInAs')}
              <b className="block font-medium text-sidebar-foreground">{me.user.name}</b>
              {detail.length > 0 ? <span className="block">{detail}</span> : null}
            </DropdownMenu.Label>
            <DropdownMenu.Separator className="mx-1 my-1 h-px bg-sidebar-border" />
            {links.map((d) => (
              <DropdownMenu.Item key={d.id} asChild className={MENU_ITEM}>
                <Link href={d.href} onClick={() => setOpenMobile(false)}>
                  {t(d.labelKey)}
                </Link>
              </DropdownMenu.Item>
            ))}
            <DropdownMenu.Separator className="mx-1 my-1 h-px bg-sidebar-border" />
            <DropdownMenu.Item
              className={MENU_ITEM}
              disabled={signOut.isPending}
              onSelect={() => {
                signOut.mutate(undefined, { onSettled: () => router.replace('/sign-in') });
              }}
            >
              {signOut.isPending ? t('shell.signingOut') : t('shell.signOut')}
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
