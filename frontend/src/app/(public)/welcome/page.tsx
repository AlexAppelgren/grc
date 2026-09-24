import type { Metadata } from 'next';

import { PublicPage } from '@/components/public/PublicPage';
import { createT, defaultLocale } from '@/shared/i18n';

const t = createT(defaultLocale);

export const metadata: Metadata = {
  title: { absolute: t('public.meta.title') },
  description: t('public.meta.description'),
};

// The public page (design/public/index.html). A person without a session ends
// up here from any gated address (SessionGate), and after signing out.
export default function WelcomePage() {
  return <PublicPage />;
}
