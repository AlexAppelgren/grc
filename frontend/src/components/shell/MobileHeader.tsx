'use client';

import Link from 'next/link';

import { Logo } from '@/components/shell/Logo';

// The compact header, below 1024 px: the phonetic mark (64px, in the page's
// text colour) as a link to Today, at the top of the page and never sticky,
// so it scrolls away (design/system/navigation.md 12). The tab bar carries no
// brand, and the product is sold under its own wordmark (DECISIONS D-05).
// There is no menu button: the tab bar and its More sheet hold every
// destination.
export function MobileHeader() {
  return (
    <header data-mobile-header="" className="mb-4 flex h-8 items-center lg:hidden">
      <Link href="/" className="block text-fg">
        <Logo className="block h-auto w-[64px]" />
      </Link>
    </header>
  );
}
