'use client';

import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useId, useState } from 'react';

import { NavIcon } from '@/components/shell/NavIcon';
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/components/ui/sidebar';
import { isDemoFrame } from '@/features/demo/frame';
import { useSession, useSetLanguage, useSignOut } from '@/features/identity/hooks';
import type { Me } from '@/features/identity/types';
import { useLanguages } from '@/features/tenant-admin/hooks';
import type { LanguageRef } from '@/features/tenant-admin/types';
import { isLocale } from '@/shared/i18n';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { ACCOUNT_PARENT, childDestinations, PUBLIC_HOME } from '@/shared/navigation/registry';

// The signed-in person as one quiet row in the rail's footer: name, then
// organisation and roles, and a menu for my passkeys, my sessions, the
// interface language and sign out. No avatar, no bordered card (the "who"
// panel it replaces). The prototype's "Switch user" never ships
// (design/README.md). Below 1024 px the More sheet lays the same account out
// flat (MoreSheet.tsx).
//
// `data-who-panel` stays on the row's wrapper because the E2E journeys locate
// the signed-in person by it. The menu renders without a portal, so its items
// are descendants of that wrapper while it is open.

const MENU_ITEM =
  'flex w-full cursor-pointer items-center rounded-md px-2 py-1.5 text-body text-sidebar-foreground no-underline outline-hidden data-[highlighted]:bg-sidebar-accent data-[disabled]:opacity-45';

export function secondLine(organisation: string | null, roles: string, t: ReturnType<typeof useT>): string {
  if (organisation !== null && roles.length > 0) return t('shell.orgRoles', { organisation, roles });
  return organisation ?? roles;
}

/** The line under the name. Platform staff have no organisation and hold platform roles (Library editor). */
export function accountLine(me: Me, t: ReturnType<typeof useT>): string {
  const roles = [...me.roles, ...me.platformRoles].map((role) => role.label).join(', ');
  return secondLine(me.tenant?.name ?? null, roles, t);
}

/**
 * The interface languages a person can choose and the choice itself (I18N-02),
 * shared by the rail's menu and the More sheet. Language rows name themselves
 * ("Svenska"); only those the interface has a catalog for are offered, the
 * rest are content languages (I18N-01). Choosing the language in use saves nothing.
 */
export function useInterfaceLanguages(): { options: LanguageRef[]; choose: (key: string) => void; pending: boolean; failed: boolean } {
  const { me } = useSession();
  const languages = useLanguages(me !== null);
  const setLanguage = useSetLanguage();
  return {
    options: (languages.data ?? []).filter((row) => isLocale(row.key)),
    choose: (key) => {
      if (isLocale(key) && key !== me?.user.locale) setLanguage.mutate(key);
    },
    pending: setLanguage.isPending,
    failed: setLanguage.isError,
  };
}

/**
 * Signs out, then leaves for the public page whatever the server answered. The rail's menu and the More sheet share it.
 * In the public page's demo there is no session to end, so it starts the demo over at Today instead of framing the page in itself.
 */
export function useSignOutToPublicPage(): { pending: boolean; signOut: () => void } {
  const router = useRouter();
  const signOut = useSignOut(() => router.replace(isDemoFrame() ? '/' : PUBLIC_HOME));
  return { pending: signOut.isPending, signOut: () => signOut.mutate() };
}

export function AccountMenu() {
  const t = useT();
  const locale = useLocale();
  const { me } = useSession();
  const { isCompact } = useSidebar();
  const { pending, signOut } = useSignOutToPublicPage();
  const languages = useInterfaceLanguages();
  const languageLabel = useId();
  const languageError = useId();
  // Crossing 1024 px hides the rail under an open menu, which would leave its
  // aria-hidden on the page and pointer-events off on body. Close it, during
  // render as React advises for state that follows a value (an effect would
  // be react-hooks/set-state-in-effect), and focus the page on close.
  const [open, setOpen] = useState(false);
  const [seenCompact, setSeenCompact] = useState(isCompact);
  if (seenCompact !== isCompact) {
    setSeenCompact(isCompact);
    setOpen(false);
  }

  // The session gate renders the shell only for a signed-in person.
  if (me === null) return null;

  const detail = accountLine(me, t);
  const links = childDestinations(ACCOUNT_PARENT, me.permissions);

  return (
    <SidebarMenu data-who-panel="">
      <SidebarMenuItem>
        <DropdownMenu.Root open={open} onOpenChange={setOpen}>
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
            side="right"
            align="end"
            sideOffset={8}
            className="z-50 min-w-56 rounded-md border border-sidebar-border bg-sidebar p-1 text-sidebar-foreground"
            onCloseAutoFocus={(event) => {
              // The rail, and the trigger with it, is hidden below 1024 px.
              if (isCompact) {
                event.preventDefault();
                document.getElementById('main')?.focus();
              }
            }}
          >
            <DropdownMenu.Label className="px-2 py-1.5 text-meta text-sidebar-muted-foreground">
              {t('shell.signedInAs')}
              <b className="block font-medium text-sidebar-foreground">{me.user.name}</b>
              {detail.length > 0 ? <span className="block">{detail}</span> : null}
            </DropdownMenu.Label>
            <DropdownMenu.Separator className="mx-1 my-1 h-px bg-sidebar-border" />
            {links.map((d) => (
              <DropdownMenu.Item key={d.id} asChild className={MENU_ITEM}>
                <Link href={d.href}>{t(d.labelKey)}</Link>
              </DropdownMenu.Item>
            ))}
            <DropdownMenu.Separator className="mx-1 my-1 h-px bg-sidebar-border" />
            {languages.options.length > 1 ? (
              <>
                <DropdownMenu.Label id={languageLabel} className="px-2 py-1.5 text-meta text-sidebar-muted-foreground">
                  {t('language.label')}
                </DropdownMenu.Label>
                <DropdownMenu.RadioGroup
                  aria-labelledby={languageLabel}
                  aria-describedby={languages.failed ? languageError : undefined}
                  value={locale}
                  onValueChange={languages.choose}
                >
                  {languages.options.map((row) => (
                    // Stays open on a choice, so the menu itself is seen to change language.
                    <DropdownMenu.RadioItem
                      key={row.key}
                      value={row.key}
                      lang={row.key}
                      disabled={languages.pending}
                      className={`${MENU_ITEM} justify-between gap-2`}
                      onSelect={(event) => event.preventDefault()}
                    >
                      {row.label}
                      <DropdownMenu.ItemIndicator>
                        <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4 fill-current">
                          <circle cx="12" cy="12" r="4" />
                        </svg>
                      </DropdownMenu.ItemIndicator>
                    </DropdownMenu.RadioItem>
                  ))}
                </DropdownMenu.RadioGroup>
                {/* A live region, not an alert: a menu owns only its items and groups
                    (ARIA 1.2), and Radix hides the rest of the page while the menu is
                    open, so the failure is read out from inside it. */}
                <div id={languageError} aria-live="polite" className="px-2 py-1.5 text-meta text-negative empty:hidden">
                  {languages.failed ? t('language.failed') : null}
                </div>
                <DropdownMenu.Separator className="mx-1 my-1 h-px bg-sidebar-border" />
              </>
            ) : null}
            <DropdownMenu.Item className={MENU_ITEM} disabled={pending} onSelect={signOut}>
              {pending ? t('shell.signingOut') : t('shell.signOut')}
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
