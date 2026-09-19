'use client';

import Link from 'next/link';

import { Logo } from '@/components/shell/Logo';
import { SidebarTrigger } from '@/components/ui/sidebar';

// The phone header: the phonetic mark (96px, in the page's text colour) on
// the left and the menu trigger on the right, where the thumb is
// (design/README.md: on phones, actions sit on the right). The trigger opens
// the rail as an off-canvas sheet from the left, where the rail lives on
// desktop, holding every destination and the account menu. The sheet
// replaces the old dock (ADR 0020 amendment 2026-09-19): the dock carried
// only dock-ranked destinations, so Roadmap, Admin and anything the registry
// adds later had no route on a phone.
export function MobileHeader() {
  return (
    <header data-mobile-header="" className="mb-4 flex items-center justify-between gap-2 md:hidden">
      <Link href="/" className="block text-fg">
        <Logo className="block h-auto w-[96px]" />
      </Link>
      <SidebarTrigger className="-mr-2" />
    </header>
  );
}
