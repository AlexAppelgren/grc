import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';

import { Providers } from '@/app/providers';
import { productName } from '@/shared/brand';
import { defaultLocale } from '@/shared/i18n';

import '@/styles/globals.css';

export const metadata: Metadata = {
  title: { default: productName, template: `%s · ${productName}` },
};

// viewport-fit=cover makes env(safe-area-inset-*) real on iPhone, so the tab
// bar clears the home indicator and the gutter clears the notch
// (design/system/navigation.md 7). Width and scale are written out rather
// than left to Next's defaults. Never a maximum scale: zoom stays (WCAG 1.4.4).
export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover' };

// `lang` comes from the UI language (I18N-02). Phase 0 has no session, so it
// is the configured default; Phase 1 reads the user's language.
export default function RootLayout({ children }: { children: ReactNode }) {
  const locale = defaultLocale;
  return (
    <html lang={locale} suppressHydrationWarning>
      <body>
        <Providers locale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
