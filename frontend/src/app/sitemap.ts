import type { MetadataRoute } from 'next';

import { hostSettingsFrom } from '@/shared/navigation/hosts';
import { PUBLIC_HOME } from '@/shared/navigation/registry';

// The one page crawlers may list (robots.txt): the public page, at / on its own
// host once the site and the app are split (src/proxy.ts), else at /welcome.
// Read per request, so the same build serves both.
export const dynamic = 'force-dynamic';

export default function sitemap(): MetadataRoute.Sitemap {
  const split = hostSettingsFrom(process.env);
  return [{ url: split === null ? `https://bleqq.com${PUBLIC_HOME}` : `https://${split.publicHosts[0]}/` }];
}
