import type { Metadata } from 'next';

import { PublicPage } from '@/components/public/PublicPage';
import { createT, defaultLocale } from '@/shared/i18n';

const t = createT(defaultLocale);

export const metadata: Metadata = {
  title: { absolute: t('public.meta.title') },
  description: t('public.meta.description'),
};

// The public page (design/public/index.html). An anonymous visitor at / lands
// here (SessionGate); every other gated address still sends them to sign in.
export default function WelcomePage() {
  return <PublicPage />;
}
