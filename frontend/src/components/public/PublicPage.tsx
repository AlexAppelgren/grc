import Link from 'next/link';
import type { ReactNode } from 'react';

import { SampleRecord } from '@/components/public/SampleRecord';
import { ThemeSwitch } from '@/components/public/ThemeSwitch';
import { Logo } from '@/components/shell/Logo';
import { buttonVariants } from '@/components/ui/Button';
import { supportContact } from '@/shared/brand';
import { createT, defaultLocale, type MessageKey } from '@/shared/i18n';
import { SIGN_IN } from '@/shared/navigation/registry';
import { cn } from '@/shared/utils/cn';

// The public page (design/public/index.html, approved by Alex 2026-09-24): a
// legal instrument on paper, with the brand green as a sticky ribbon and one
// closing field. Every section carries a marginal section reference, the way
// a statute carries marginal headings. Hierarchy comes from type and the two
// greys, so colour is kept to the section references and the double rules, and
// running prose is set at 16 px. Colours are token utilities only; the serif
// faces are loaded by the (public) layout.

const t = createT(defaultLocale);

// The page gutter, as AppShell writes it: 16 px, then 32 px from md, each the
// larger of that step and the safe-area inset (foundations.md "Spacing").
const WRAP =
  'mx-auto w-full max-w-[1160px] pr-[max(1rem,env(safe-area-inset-right))] pl-[max(1rem,env(safe-area-inset-left))] md:pr-[max(2rem,env(safe-area-inset-right))] md:pl-[max(2rem,env(safe-area-inset-left))]';

// A jump lands below the sticky bar (57 px on a phone, 61 px from lg).
const ANCHOR = 'scroll-mt-[76px]';

// The top bar sits on the page's own paper (Alex, 2026-09-24: too many colours
// competing). Sign in is the app's neutral primary and always on screen;
// Request access is the outline beside it, on its left. On a phone both drop to
// the meta size so the row fits at 320 px. buttonVariants hovers on `enabled:`,
// which a link never matches, so the hover is added here.
const BAR_BUTTON = 'max-sm:px-2.5 max-sm:text-meta';
const BAR_PRIMARY = cn(buttonVariants({ variant: 'primary', size: 'small' }), BAR_BUTTON, 'hover:bg-[color-mix(in_srgb,var(--color-button)_88%,var(--color-page))]');
const BAR_SECONDARY = cn(buttonVariants({ variant: 'outline', size: 'small' }), BAR_BUTTON, 'hover:hover-fill');

// On the closing field, the one green surface left on the page.
const ON_BRAND_PRIMARY =
  'inline-flex h-8 items-center rounded-control border border-on-brand bg-on-brand px-2.5 text-meta font-medium whitespace-nowrap text-brand hover:opacity-90 sm:px-3 sm:text-body';
const ON_BRAND_SECONDARY =
  'inline-flex h-8 items-center rounded-control border border-on-brand-line px-2.5 text-meta font-medium whitespace-nowrap text-on-brand hover:bg-on-brand-hover sm:px-3 sm:text-body';

const FOOT_LINK = 'text-muted hover:text-fg hover:underline hover:underline-offset-4';

const SECTIONS: readonly (readonly [string, MessageKey])[] = [
  ['method', 'public.nav.method'],
  ['zones', 'public.nav.zones'],
  ['coverage', 'public.nav.coverage'],
  ['assurance', 'public.nav.assurance'],
  ['questions', 'public.nav.questions'],
];

const CASE: readonly (readonly [MessageKey, MessageKey])[] = [
  ['public.case.version.title', 'public.case.version.body'],
  ['public.case.decision.title', 'public.case.decision.body'],
  ['public.case.coverage.title', 'public.case.coverage.body'],
];

const WHAT: readonly (readonly [MessageKey, MessageKey, MessageKey])[] = [
  ['public.what.inventory.kicker', 'public.what.inventory.title', 'public.what.inventory.body'],
  ['public.what.watch.kicker', 'public.what.watch.title', 'public.what.watch.body'],
  ['public.what.ask.kicker', 'public.what.ask.title', 'public.what.ask.body'],
  ['public.what.evidence.kicker', 'public.what.evidence.title', 'public.what.evidence.body'],
];

const STEPS: readonly (readonly [MessageKey, MessageKey, MessageKey])[] = [
  ['public.method.sighted.name', 'public.method.sighted.body', 'public.method.actor.agent'],
  ['public.method.proposed.name', 'public.method.proposed.body', 'public.method.actor.agent'],
  ['public.method.confirmed.name', 'public.method.confirmed.body', 'public.method.actor.secondAgent'],
  ['public.method.applied.name', 'public.method.applied.body', 'public.method.actor.library'],
  ['public.method.assessed.name', 'public.method.assessed.body', 'public.method.actor.bank'],
  ['public.method.signedOff.name', 'public.method.signedOff.body', 'public.method.actor.bank'],
];

const COVERAGE: readonly (readonly [MessageKey, MessageKey, MessageKey])[] = [
  ['public.coverage.se.name', 'public.coverage.se.sources', 'public.coverage.se.languages'],
  ['public.coverage.dk.name', 'public.coverage.dk.sources', 'public.coverage.dk.languages'],
  ['public.coverage.no.name', 'public.coverage.no.sources', 'public.coverage.no.languages'],
  ['public.coverage.fi.name', 'public.coverage.fi.sources', 'public.coverage.fi.languages'],
  ['public.coverage.eu.name', 'public.coverage.eu.sources', 'public.coverage.eu.languages'],
];

const COVERAGE_HEADS: readonly MessageKey[] = ['public.coverage.head.jurisdiction', 'public.coverage.head.sources', 'public.coverage.head.languages'];

const ASSURANCE: readonly (readonly [MessageKey, MessageKey])[] = [
  ['public.assurance.access.term', 'public.assurance.access.body'],
  ['public.assurance.fourEyes.term', 'public.assurance.fourEyes.body'],
  ['public.assurance.isolation.term', 'public.assurance.isolation.body'],
  ['public.assurance.models.term', 'public.assurance.models.body'],
  ['public.assurance.ledger.term', 'public.assurance.ledger.body'],
  ['public.assurance.retention.term', 'public.assurance.retention.body'],
  ['public.assurance.leaving.term', 'public.assurance.leaving.body'],
  ['public.assurance.pack.term', 'public.assurance.pack.body'],
];

const QUESTIONS: readonly (readonly [MessageKey, MessageKey])[] = [
  ['public.questions.ai.q', 'public.questions.ai.a'],
  ['public.questions.oneEntity.q', 'public.questions.oneEntity.a'],
  ['public.questions.whoSees.q', 'public.questions.whoSees.a'],
  ['public.questions.libraryWrong.q', 'public.questions.libraryWrong.a'],
  ['public.questions.getIn.q', 'public.questions.getIn.a'],
  ['public.questions.cost.q', 'public.questions.cost.a'],
];

/** The printed document's break: a 3 px rule over a 1 px rule. */
function DoubleRule({ onBrand = false }: { onBrand?: boolean }) {
  return (
    <div
      aria-hidden="true"
      className={cn('mb-7 h-[7px] border-t-[3px] border-b', onBrand ? 'border-t-on-brand border-b-on-brand-line' : 'border-accent')}
    />
  );
}

/** A numbered section: the marginal reference on the left, the body on the right. Its break is the double rule alone. */
function Section({ id, number, headingKey, children }: { id: string; number: number; headingKey: MessageKey; children: ReactNode }) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={cn(ANCHOR, 'grid py-11 md:grid-cols-[120px_minmax(0,1fr)] md:gap-10 md:py-20 lg:gap-14')}
    >
      <p className="mb-5 font-mono text-body font-medium text-brass md:mb-0">{t('public.sectionRef', { number: String(number) })}</p>
      <div className="min-w-0">
        <DoubleRule />
        <h2 id={`${id}-title`} className="mb-5 font-serif text-display font-normal text-balance">
          {t(headingKey)}
        </h2>
        {children}
      </div>
    </section>
  );
}

export function PublicPage() {
  const writeTo =
    supportContact === '' ? null : `mailto:${supportContact}?subject=${encodeURIComponent(t('public.request.mailSubject'))}`;
  return (
    <>
      <a
        href="#top"
        className="sr-only focus:not-sr-only focus:absolute focus:top-[max(8px,env(safe-area-inset-top))] focus:left-[max(8px,env(safe-area-inset-left))] focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2"
      >
        {t('shell.skipToContent')}
      </a>

      <header className="sticky top-[env(safe-area-inset-top,0px)] z-20 border-b border-line bg-page text-fg">
        <div className={cn(WRAP, 'flex flex-wrap items-center gap-3 py-3 lg:gap-5 lg:py-3.5')}>
          <a href="#top" className="shrink-0 pr-1.5">
            <Logo className="block h-auto w-20 sm:w-24" />
          </a>
          <nav aria-label={t('public.nav.label')} className="ml-auto hidden gap-5 lg:flex">
            {SECTIONS.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="text-body text-muted hover:text-fg">
                {t(label)}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2 lg:ml-3">
            <a href="#request" className={BAR_SECONDARY}>
              {t('public.action.requestAccess')}
            </a>
            <Link href={SIGN_IN} className={BAR_PRIMARY}>
              {t('public.action.signIn')}
            </Link>
          </div>
        </div>
      </header>

      <main id="top" className={ANCHOR}>
        <div className={WRAP}>
          {/* One thing on the first screen: the headline and one line under it. The
              actions live in the sticky bar, and the sample record in § 3, where it is
              the worked example of the six steps (Alex, 2026-09-24: the page was
              cluttered and nothing drew the eye). */}
          <section aria-labelledby="public-title" className="pt-14 pb-16 md:pt-24 md:pb-24">
            <p className="microlabel mb-5 font-mono text-muted">{t('public.hero.eyebrow')}</p>
            <h1 id="public-title" className="max-w-[20ch] font-serif-display text-hero text-balance">
              {t('public.hero.title')}
            </h1>
            <p className="mt-6 max-w-[52ch] text-title font-normal text-muted">{t('public.hero.deck')}</p>
          </section>

          <Section id="case" number={1} headingKey="public.case.title">
            <div className="max-w-[62ch] text-title font-normal">
              <p className="mb-4 font-serif text-title font-normal italic">{t('public.case.lede')}</p>
              <p>{t('public.case.body')}</p>
            </div>
            <ul className="mt-7 border-t border-line">
              {CASE.map(([title, body]) => (
                <li key={title} className="border-b border-line py-4">
                  <h3 className="mb-1 text-title">{t(title)}</h3>
                  <p className="text-title font-normal text-muted">{t(body)}</p>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="what" number={2} headingKey="public.what.title">
            <div className="grid gap-x-12 md:grid-cols-2">
              {WHAT.map(([kicker, title, body]) => (
                <div key={kicker} className="border-t border-line py-4.5">
                  <p className="mb-2 font-mono text-meta text-muted">{t(kicker)}</p>
                  <h3 className="mb-1.5 text-title">{t(title)}</h3>
                  <p className="text-title font-normal text-muted">{t(body)}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section id="method" number={3} headingKey="public.method.title">
            <ol className="border-t border-line">
              {STEPS.map(([name, body, actor], index) => (
                <li
                  key={name}
                  className="grid grid-cols-[24px_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1 border-b border-line py-3.5 sm:grid-cols-[34px_minmax(0,1fr)_auto] sm:gap-x-4"
                >
                  <span className="font-mono text-meta text-muted tabular-nums">{index + 1}</span>
                  <span className="text-title font-normal">
                    <b className="font-semibold">{t(name)}</b> {t(body)}
                  </span>
                  <span className="col-start-2 font-mono text-meta text-muted sm:col-start-auto">{t(actor)}</span>
                </li>
              ))}
            </ol>
            <div className="mt-8 max-w-[560px]">
              <SampleRecord />
            </div>
            <p className="mt-5 max-w-[62ch] text-muted">{t('public.method.footnote')}</p>
          </Section>

          <Section id="zones" number={4} headingKey="public.zones.title">
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:gap-7">
              <div className="rounded-card border border-line bg-surface p-4">
                <h3 className="mb-1.5 text-title">{t('public.zones.library.title')}</h3>
                <p className="text-title font-normal text-muted">{t('public.zones.library.body')}</p>
              </div>
              <div className="flex items-center justify-center gap-2.5 text-center md:min-w-[118px] md:flex-col">
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="size-5 rotate-90 text-muted md:rotate-0">
                  <path d="M4 12h16M14 6l6 6-6 6" />
                </svg>
                <span className="microlabel text-muted">{t('public.zones.door.label')}</span>
                <span className="max-w-[16ch] text-meta text-muted">{t('public.zones.door.body')}</span>
              </div>
              <div className="rounded-card border border-line bg-subtle p-4">
                <h3 className="mb-1.5 text-title">{t('public.zones.yours.title')}</h3>
                <p className="text-title font-normal text-muted">{t('public.zones.yours.body')}</p>
              </div>
            </div>
            <p className="mt-6 max-w-[62ch] text-muted">{t('public.zones.footnote')}</p>
          </Section>

          <Section id="coverage" number={5} headingKey="public.coverage.title">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {COVERAGE_HEADS.map((head) => (
                      <th key={head} scope="col" className="microlabel border-b border-line pr-4 pb-3.5 text-left text-muted">
                        {t(head)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {COVERAGE.map(([name, sources, languages]) => (
                    <tr key={name}>
                      <th scope="row" className="border-b border-line py-3.5 pr-4 text-left align-top font-semibold">
                        {t(name)}
                      </th>
                      <td className="border-b border-line py-3.5 pr-4 align-top text-muted">{t(sources)}</td>
                      <td className="border-b border-line py-3.5 align-top text-muted">{t(languages)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="assurance" number={6} headingKey="public.assurance.title">
            <dl className="border-t border-line">
              {ASSURANCE.map(([term, body]) => (
                <div key={term} className="grid gap-1 border-b border-line py-3.5 sm:grid-cols-[30%_minmax(0,1fr)] sm:gap-4">
                  <dt className="text-title">{t(term)}</dt>
                  <dd className="m-0 text-title font-normal text-muted">{t(body)}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section id="questions" number={7} headingKey="public.questions.title">
            <div className="grid gap-x-12 md:grid-cols-2">
              {QUESTIONS.map(([question, answer]) => (
                <div key={question} className="border-t border-line py-4.5">
                  <h3 className="mb-1.5 font-serif text-title font-normal">{t(question)}</h3>
                  <p className="text-title font-normal text-muted">{t(answer)}</p>
                </div>
              ))}
            </div>
          </Section>
        </div>

        <section id="request" aria-labelledby="request-title" className={cn(ANCHOR, 'bg-brand text-on-brand')}>
          <div className={cn(WRAP, 'py-12 md:py-20')}>
            <DoubleRule onBrand />
            <h2 id="request-title" className="font-serif-display text-hero text-balance">
              {t('public.request.title')}
            </h2>
            <p className="mt-5 max-w-[56ch] text-title font-normal text-on-brand-muted">
              {t('public.request.invited')}
              {writeTo === null ? null : <> {t('public.request.introduce')}</>}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              {writeTo === null ? null : (
                <a href={writeTo} className={cn(ON_BRAND_PRIMARY, 'h-9 px-4 text-body')}>
                  {t('public.request.write')}
                </a>
              )}
              <Link href={SIGN_IN} className={cn(ON_BRAND_SECONDARY, 'h-9 px-4 text-body')}>
                {t('public.action.signIn')}
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className={cn(WRAP, 'pt-10 pb-7 md:pt-14')}>
          <div className="grid gap-8 pb-7 sm:grid-cols-2 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <Logo className="block h-auto w-30 text-fg" />
              <p className="mt-3.5 font-mono text-meta text-muted">{t('public.footer.pronounced')}</p>
            </div>
            <nav aria-labelledby="footer-sections">
              <p id="footer-sections" className="microlabel mb-3 text-muted">
                {t('public.footer.onThisPage')}
              </p>
              <ul className="grid gap-2">
                {SECTIONS.map(([id, label]) => (
                  <li key={id}>
                    <a href={`#${id}`} className={FOOT_LINK}>
                      {t(label)}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
            <div>
              <p className="microlabel mb-3 text-muted">{t('public.footer.account')}</p>
              <ul className="grid gap-2">
                <li>
                  <Link href={SIGN_IN} className={FOOT_LINK}>
                    {t('public.action.signIn')}
                  </Link>
                </li>
                <li>
                  <a href="#request" className={FOOT_LINK}>
                    {t('public.action.requestAccess')}
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-x-7 gap-y-3 border-t border-line pt-5 font-mono text-meta text-muted">
            <span>{t('public.footer.copyright', { year: String(new Date().getFullYear()) })}</span>
            <span>{t('public.footer.colophon')}</span>
            <ThemeSwitch />
          </div>
        </div>
      </footer>
    </>
  );
}
