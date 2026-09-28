import type { Metadata } from 'next';
import type { ReactNode } from 'react';

// Pages anyone can read, outside the session gate and the shell
// (design/public/). The serif faces load here and nowhere else, so no
// signed-in screen downloads them.
import '@fontsource/libre-caslon-display/400.css';
import '@fontsource/libre-caslon-text/400.css';
import '@fontsource/libre-caslon-text/400-italic.css';

// The one group a search engine and a web filter's categoriser may index
// (robots.txt, sitemap.xml); every other page inherits the root's noindex.
export const metadata: Metadata = { robots: { index: true, follow: true } };

export default function PublicLayout({ children }: { children: ReactNode }) {
  return children;
}
