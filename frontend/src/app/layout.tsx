import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { Providers } from '@/app/providers';
import { productName } from '@/shared/brand';
import { defaultLocale } from '@/shared/i18n';

import '@/styles/globals.css';

export const metadata: Metadata = {
  title: { default: productName, template: `%s · ${productName}` },
};

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
