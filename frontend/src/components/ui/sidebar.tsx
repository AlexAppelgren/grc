'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { Slot } from '@radix-ui/react-slot';
import * as Tooltip from '@radix-ui/react-tooltip';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ComponentProps,
  type CSSProperties,
  type ReactNode,
} from 'react';

import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// The parts of shadcn/ui's Sidebar (ui.shadcn.com/docs/components/base/sidebar)
// that the shell renders, written by hand with shadcn's names so the API is
// familiar (ADR 0004: our own components on Green tokens; the shadcn CLI
// would rewrite the Tailwind and CSS-variable setup). A part nothing renders
// is left out and added the day a screen needs it.
//
// The look follows seb.io's own rail: a quiet neutral surface, a hairline
// border, compact rows of a small icon and a label, groups separated by
// space. Colour comes only from the --sidebar-* tokens in theme.css, which
// resolve to Green tokens. The current row is shadcn's treatment, not
// seb.io's fully rounded pill: a small radius, a subtle neutral accent and
// medium weight on data-[active=true], so the fully rounded shape stays
// <Pill>'s alone (playbook 6.7).

// foundations.md "Sidebar row": 240px, 48px collapsed (shadcn's 3rem), 280px
// as a phone sheet.
const WIDTH = '15rem';
const WIDTH_ICON = '3rem';
const WIDTH_MOBILE = '17.5rem';

/**
 * localStorage, not shadcn's cookie: the API owns the cookie jar and its
 * refresh cookie is SameSite=Strict on a scoped path. No tenant content.
 */
export const SIDEBAR_STORAGE_KEY = 'bleqq.sidebar.open';

/** Below Tailwind's `md`, the rail becomes the off-canvas sheet. */
const MOBILE_QUERY = '(max-width: 767px)';

/** The stored open state; `null` when nothing is stored or storage throws (private mode). */
export function readStoredOpen(): boolean | null {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    return raw === 'true' ? true : raw === 'false' ? false : null;
  } catch {
    return null;
  }
}

function writeStoredOpen(open: boolean): void {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(open));
  } catch {
    // Storage unavailable: the rail still collapses, it just forgets.
  }
}

// Storage and the viewport are read with useSyncExternalStore, not copied
// into state from an effect: the server snapshot (expanded, desktop) is what
// the server renders, so hydration never mismatches.
function subscribeStorage(onChange: () => void): () => void {
  window.addEventListener('storage', onChange);
  return () => window.removeEventListener('storage', onChange);
}

function subscribeMobile(onChange: () => void): () => void {
  const query = window.matchMedia(MOBILE_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

const isMobileNow = (): boolean => window.matchMedia(MOBILE_QUERY).matches;
const onServer = (): null => null;
const notMobileOnServer = (): boolean => false;

interface SidebarContextValue {
  state: 'expanded' | 'collapsed';
  isMobile: boolean;
  openMobile: boolean;
  setOpenMobile: (open: boolean) => void;
  toggleSidebar: () => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

export function useSidebar(): SidebarContextValue {
  const context = useContext(SidebarContext);
  if (context === null) throw new Error('useSidebar must be used inside a <SidebarProvider>.');
  return context;
}

export function SidebarProvider({ children }: { children: ReactNode }) {
  const isMobile = useSyncExternalStore(subscribeMobile, isMobileNow, notMobileOnServer);
  const stored = useSyncExternalStore(subscribeStorage, readStoredOpen, onServer);
  // This mount's choice wins over the stored one, so the rail still toggles
  // when storage throws.
  const [chosen, setChosen] = useState<boolean | null>(null);
  const [openMobile, setOpenMobile] = useState(false);
  const open = chosen ?? stored ?? true;

  const toggleSidebar = useCallback(() => {
    if (isMobile) {
      setOpenMobile(!openMobile);
      return;
    }
    setChosen(!open);
    writeStoredOpen(!open);
  }, [isMobile, openMobile, open]);

  // ctrl+b / cmd+b, as shadcn ships it.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'b' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toggleSidebar]);

  const value = useMemo<SidebarContextValue>(
    () => ({ state: open ? 'expanded' : 'collapsed', isMobile, openMobile, setOpenMobile, toggleSidebar }),
    [open, isMobile, openMobile, toggleSidebar],
  );

  return (
    <SidebarContext.Provider value={value}>
      <Tooltip.Provider delayDuration={0}>
        <div
          data-slot="sidebar-wrapper"
          style={{ '--sidebar-width': WIDTH, '--sidebar-width-icon': WIDTH_ICON, '--sidebar-width-mobile': WIDTH_MOBILE } as CSSProperties}
          className="flex min-h-svh w-full"
        >
          {children}
        </div>
      </Tooltip.Provider>
    </SidebarContext.Provider>
  );
}

/** The rail: collapses to icons on desktop, an off-canvas sheet from the left on phones. */
export function Sidebar({ children }: { children: ReactNode }) {
  const t = useT();
  const { isMobile, state, openMobile, setOpenMobile } = useSidebar();

  if (isMobile) {
    return (
      <Dialog.Root open={openMobile} onOpenChange={setOpenMobile}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-fg/50" />
          <Dialog.Content
            data-slot="sidebar"
            className="fixed inset-y-0 left-0 z-50 flex h-svh w-[var(--sidebar-width-mobile)] flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
          >
            <Dialog.Title className="sr-only">{t('sidebar.title')}</Dialog.Title>
            <Dialog.Description className="sr-only">{t('sidebar.description')}</Dialog.Description>
            {children}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );
  }

  // data-collapsible drives every collapsed style below through group-data.
  return (
    <div className="group peer hidden text-sidebar-foreground md:block" data-slot="sidebar" data-state={state} data-collapsible={state === 'collapsed' ? 'icon' : ''}>
      {/* Holds the rail's width in the flex row; the rail itself is fixed so it never scrolls with the page. */}
      <div className="h-svh w-[var(--sidebar-width)] transition-[width] duration-200 ease-linear group-data-[collapsible=icon]:w-[var(--sidebar-width-icon)]" />
      <div className="fixed inset-y-0 left-0 z-10 flex h-svh w-[var(--sidebar-width)] flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-linear group-data-[collapsible=icon]:w-[var(--sidebar-width-icon)]">
        {children}
      </div>
    </div>
  );
}

export function SidebarTrigger({ className }: { className?: string }) {
  const t = useT();
  const { toggleSidebar } = useSidebar();
  return (
    <button
      type="button"
      data-sidebar="trigger"
      aria-label={t('sidebar.toggle')}
      className={cn('inline-flex size-8 items-center justify-center rounded-md text-fg hover:bg-sidebar-hover', className)}
      onClick={toggleSidebar}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4 fill-none stroke-current stroke-[1.75] [stroke-linecap:round]">
        <path d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
  );
}

export function SidebarInset(props: ComponentProps<'main'>) {
  return <main {...props} className={cn('relative flex min-h-svh w-full min-w-0 flex-1 flex-col', props.className)} />;
}

export function SidebarHeader(props: ComponentProps<'div'>) {
  return <div {...props} className={cn('flex flex-col p-3', props.className)} />;
}

export function SidebarContent({ children }: { children: ReactNode }) {
  // Scrolls if a long registry needs it, but never shows a scrollbar.
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-auto [scrollbar-width:none] group-data-[collapsible=icon]:overflow-hidden [&::-webkit-scrollbar]:hidden">
      {children}
    </div>
  );
}

export function SidebarFooter(props: ComponentProps<'div'>) {
  return <div {...props} className={cn('mt-auto flex flex-col gap-0.5 p-2', props.className)} />;
}

/** One group of rows. Groups are separated by space, as seb.io does it, not by a rule or a heading. */
export function SidebarGroup(props: ComponentProps<'div'>) {
  return <div {...props} className={cn('flex w-full min-w-0 flex-col px-2 py-1.5', props.className)} />;
}

export function SidebarMenu(props: ComponentProps<'ul'>) {
  return <ul {...props} className="flex w-full min-w-0 flex-col gap-0.5" />;
}

export function SidebarMenuItem({ children }: { children: ReactNode }) {
  return <li className="relative">{children}</li>;
}

// shadcn's SidebarMenuButton sizes: default 32px (h-8) in `body`, sm 28px
// in `meta`; lg is the account row, as tall as its two lines.
const SIZES = { default: 'h-8 text-body', sm: 'h-7 text-meta', lg: 'min-h-8 py-1.5 text-body group-data-[collapsible=icon]:h-8 group-data-[collapsible=icon]:py-0' } as const;

export function SidebarMenuButton({
  asChild = false,
  isActive = false,
  size = 'default',
  tooltip,
  className,
  ...props
}: ComponentProps<'button'> & {
  /** Renders the child (a Link) as the row instead of a button. */
  asChild?: boolean;
  isActive?: boolean;
  size?: keyof typeof SIZES;
  /** Shown beside the collapsed rail, where only the icon is visible. */
  tooltip: string;
}) {
  const { isMobile, state } = useSidebar();
  const Row = asChild ? Slot : 'button';
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <Row
          type={asChild ? undefined : 'button'}
          data-active={isActive}
          className={cn(
            'flex w-full items-center gap-2 overflow-hidden rounded-md px-2 text-left text-sidebar-foreground no-underline transition-colors',
            'hover:bg-sidebar-hover',
            'data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground',
            'group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0',
            '[&>span:last-child]:truncate group-data-[collapsible=icon]:[&>span:last-child]:hidden',
            SIZES[size],
            className,
          )}
          {...props}
        />
      </Tooltip.Trigger>
      <Tooltip.Content
        side="right"
        sideOffset={8}
        hidden={state !== 'collapsed' || isMobile}
        className="z-50 rounded-md border border-line bg-surface px-2 py-1 text-meta text-fg"
      >
        {tooltip}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}
