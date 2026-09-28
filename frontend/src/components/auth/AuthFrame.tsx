import type { ReactNode } from 'react';

import { Logo } from '@/components/shell/Logo';
import { privacyContact, productName, securityContact } from '@/shared/brand';
import { createT, defaultLocale } from '@/shared/i18n';
import { PUBLIC_HOME } from '@/shared/navigation/registry';

const t = createT(defaultLocale);

// A plain link, so a page load reaches the server, which sends it to the
// public host when the app has a host of its own (src/proxy.ts).
const ABOUT_LINK = 'font-semibold underline';

// What the service is and who runs it, rendered on the server under every
// auth screen: a visitor, a crawler or a bank's web filter reads it in the
// first byte, whatever the passkey panel above is still waiting for
// (docs/runbooks/DNS_DOMAINS.md "The public site and the app on their own hosts").
function About() {
  return (
    <footer aria-labelledby="auth-about-title" className="mt-8 border-t border-line pt-4 text-meta text-muted">
      <h2 id="auth-about-title" className="microlabel mb-1.5">
        {t('auth.about.title')}
      </h2>
      <p className="mb-3">{t('auth.about.body', { product: productName })}</p>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        <dt>{t('auth.about.company')}</dt>
        <dd>
          <a href={PUBLIC_HOME} className={ABOUT_LINK}>
            {t('auth.about.companyName')}
          </a>
        </dd>
        <dt>{t('auth.about.privacy')}</dt>
        <dd>
          <a href={`mailto:${privacyContact}`} className={ABOUT_LINK}>
            {privacyContact}
          </a>
        </dd>
        <dt>{t('auth.about.security')}</dt>
        <dd>
          <a href={`mailto:${securityContact}`} className={ABOUT_LINK}>
            {securityContact}
          </a>
        </dd>
      </dl>
    </footer>
  );
}

// The auth surface (design/screens/auth-*.html): no side rail, the wordmark
// above one centred panel of at most 440px.
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen justify-items-center px-4 pt-7 pb-20 md:pt-12">
      <div className="w-full max-w-[440px]">
        <Logo className="mx-auto mb-7 block h-auto w-[150px] text-fg" />
        <main>{children}</main>
        <About />
      </div>
    </div>
  );
}

export function AuthPanel({ children, ...rest }: { children: ReactNode } & React.HTMLAttributes<HTMLElement>) {
  return (
    <section className="rounded-card border border-line bg-surface p-6" {...rest}>
      {children}
    </section>
  );
}

export function StepKicker({ children }: { children: ReactNode }) {
  return <p className="microlabel mb-1.5 text-muted">{children}</p>;
}
