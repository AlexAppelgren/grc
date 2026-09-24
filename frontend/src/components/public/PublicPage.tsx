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
// a statute carries marginal headings. Colours are token utilities only; the
// serif faces are loaded by the (public) layout.

const t = createT(defaultLocale);

// The page gutter, as AppShell writes it: 16 px, then 32 px from md, each the
// larger of that step and the safe-area inset (foundations.md "Spacing").
const WRAP =
  'mx-auto w-full max-w-[1160px] pr-[max(1rem,env(safe-area-inset-right))] pl-[max(1rem,env(safe-area-inset-left))] md:pr-[max(2rem,env(safe-area-inset-right))] md:pl-[max(2rem,env(safe-area-inset-left))]';

// A jump lands below the sticky ribbon (56 px on a phone, 60 px from lg).
const ANCHOR = 'scroll-mt-[76px]';

// On the green ribbon and the closing field. Sign in is the primary and always
// on screen; Request access is the outline beside it, on its left.
const ON_BRAND_PRIMARY =
  'inline-flex h-8 items-center rounded-control border border-on-brand bg-on-brand px-2.5 text-meta font-medium whitespace-nowrap text-brand hover:opacity-90 sm:px-3 sm:text-body';
const ON_BRAND_SECONDARY =
  'inline-flex h-8 items-center rounded-control border border-on-brand-line px-2.5 text-meta font-medium whitespace-nowrap text-on-brand hover:bg-on-brand-hover sm:px-3 sm:text-body';

// buttonVariants hovers on `enabled:`, which a link never matches.
const LINK_PRIMARY = cn(buttonVariants({ variant: 'primary' }), 'hover:bg-[color-mix(in_srgb,var(--color-button)_88%,var(--color-page))]');
const LINK_OUTLINE = cn(buttonVariants({ variant: 'outline' }), 'hover:hover-fill');

const FOOT_LINK = 'text-muted hover:text-fg hover:underline hover:underline-offset-4';

const SECTIONS: readonly (readonly [string, MessageKey])[] = [
  ['method', 'public.nav.method'],
  ['zones', 'public.nav.zones'],
  ['coverage', 'public.nav.coverage'],
  ['assurance', 'public.nav.assurance'],
  ['questions', 'public.nav.questions'],
];

const FACTS: readonly (readonly [MessageKey, MessageKey])[] = [
  ['public.facts.jurisdictions.label', 'public.facts.jurisdictions.value'],
  ['public.facts.languages.label', 'public.facts.languages.value'],
  ['public.facts.zones.label', 'public.facts.zones.value'],
  ['public.facts.changes.label', 'public.facts.changes.value'],
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

/** A numbered section: the marginal reference and note on the left, the body on the right. */
function Section({ id, number, noteKey, headingKey, children }: { id: string; number: number; noteKey: MessageKey; headingKey: MessageKey; children: ReactNode }) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={cn(ANCHOR, 'grid border-t border-line py-11 md:grid-cols-[150px_minmax(0,1fr)] md:gap-10 md:py-20 lg:gap-14')}
    >
      <p className="mb-5 flex items-baseline gap-3 font-mono text-meta text-muted md:mb-0 md:block">
        <span className="text-body font-medium text-brass md:mb-2 md:block">{t('public.sectionRef', { number: String(number) })}</span>
        <span>{t(noteKey)}</span>
      </p>
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

      <header className="sticky top-[env(safe-area-inset-top,0px)] z-20 bg-brand text-on-brand">
        <div className={cn(WRAP, 'flex flex-wrap items-center gap-3 py-3 lg:gap-5 lg:py-3.5')}>
          <a href="#top" className="shrink-0 pr-1.5">
            <Logo className="block h-auto w-20 sm:w-24" />
          </a>
          <nav aria-label={t('public.nav.label')} className="ml-auto hidden gap-5 lg:flex">
            {SECTIONS.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="text-body text-on-brand-muted hover:text-on-brand">
                {t(label)}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2 lg:ml-3">
            <a href="#request" className={ON_BRAND_SECONDARY}>
              {t('public.action.requestAccess')}
            </a>
            <Link href={SIGN_IN} className={ON_BRAND_PRIMARY}>
              {t('public.action.signIn')}
            </Link>
          </div>
        </div>
      </header>

      <main id="top" className={ANCHOR}>
        <div className={WRAP}>
          <section aria-labelledby="public-title" className="grid items-start gap-8 pt-10 pb-9 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:gap-16 lg:pt-20 lg:pb-14">
            <div>
              <p className="microlabel mb-4 font-mono text-brass">{t('public.hero.eyebrow')}</p>
              <h1 id="public-title" className="font-serif-display text-hero text-balance">
                {t('public.hero.title')}
              </h1>
              <p className="mt-5 max-w-[56ch] text-title font-normal text-muted">{t('public.hero.deck')}</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <a href="#request" className={LINK_PRIMARY}>
                  {t('public.action.requestAccess')}
                </a>
                <Link href={SIGN_IN} className={LINK_OUTLINE}>
                  {t('public.action.signIn')}
                </Link>
              </div>
            </div>
            <SampleRecord />
          </section>

          <dl className="grid gap-px border-y border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
            {FACTS.map(([label, value]) => (
              <div key={label} className="bg-page px-4 pt-4 pb-4.5">
                <dt className="microlabel mb-1.5 text-brass">{t(label)}</dt>
                <dd className="m-0 text-fg">{t(value)}</dd>
              </div>
            ))}
          </dl>

          <Section id="case" number={1} noteKey="public.case.note" headingKey="public.case.title">
            <div className="max-w-[62ch] leading-[1.375rem]">
              <p className="mb-4 font-serif text-title font-normal italic">{t('public.case.lede')}</p>
              <p>{t('public.case.body')}</p>
            </div>
            <ul className="mt-7 border-t border-line">
              {CASE.map(([title, body]) => (
                <li key={title} className="border-b border-line py-4">
                  <h3 className="mb-1 text-title">{t(title)}</h3>
                  <p className="text-muted">{t(body)}</p>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="what" number={2} noteKey="public.what.note" headingKey="public.what.title">
            <div className="grid gap-x-12 md:grid-cols-2">
              {WHAT.map(([kicker, title, body]) => (
                <div key={kicker} className="border-t border-line py-4.5">
                  <p className="mb-2 font-mono text-meta text-brass">{t(kicker)}</p>
                  <h3 className="mb-1.5 text-title">{t(title)}</h3>
                  <p className="text-muted">{t(body)}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section id="method" number={3} noteKey="public.method.note" headingKey="public.method.title">
            <ol className="border-t border-line">
              {STEPS.map(([name, body, actor], index) => (
                <li
                  key={name}
                  className="grid grid-cols-[24px_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1 border-b border-line py-3.5 sm:grid-cols-[34px_minmax(0,1fr)_auto] sm:gap-x-4"
                >
                  <span className="font-mono text-meta text-brass tabular-nums">{index + 1}</span>
                  <span>
                    <b className="font-semibold">{t(name)}</b> {t(body)}
                  </span>
                  <span className="col-start-2 font-mono text-meta text-muted sm:col-start-auto">{t(actor)}</span>
                </li>
              ))}
            </ol>
            <p className="mt-5 max-w-[62ch] text-meta text-muted">{t('public.method.footnote')}</p>
          </Section>

          <Section id="zones" number={4} noteKey="public.zones.note" headingKey="public.zones.title">
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:gap-7">
              <div className="rounded-card border border-line bg-surface p-4">
                <h3 className="mb-1.5 text-title">{t('public.zones.library.title')}</h3>
                <p className="text-muted">{t('public.zones.library.body')}</p>
              </div>
              <div className="flex items-center justify-center gap-2.5 text-center md:min-w-[118px] md:flex-col">
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="size-5 rotate-90 text-brass md:rotate-0">
                  <path d="M4 12h16M14 6l6 6-6 6" />
                </svg>
                <span className="microlabel text-brass">{t('public.zones.door.label')}</span>
                <span className="max-w-[16ch] text-meta text-muted">{t('public.zones.door.body')}</span>
              </div>
              <div className="rounded-card border border-line bg-subtle p-4">
                <h3 className="mb-1.5 text-title">{t('public.zones.yours.title')}</h3>
                <p className="text-muted">{t('public.zones.yours.body')}</p>
              </div>
            </div>
            <p className="mt-6 max-w-[62ch] text-meta text-muted">{t('public.zones.footnote')}</p>
          </Section>

          <Section id="coverage" number={5} noteKey="public.coverage.note" headingKey="public.coverage.title">
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
            <p className="mt-6 max-w-[62ch]">{t('public.coverage.footnote')}</p>
          </Section>

          <Section id="assurance" number={6} noteKey="public.assurance.note" headingKey="public.assurance.title">
            <dl className="border-t border-line">
              {ASSURANCE.map(([term, body]) => (
                <div key={term} className="grid gap-1 border-b border-line py-3.5 sm:grid-cols-[30%_minmax(0,1fr)] sm:gap-4">
                  <dt className="font-semibold">{t(term)}</dt>
                  <dd className="m-0 text-muted">{t(body)}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section id="questions" number={7} noteKey="public.questions.note" headingKey="public.questions.title">
            <div className="grid gap-x-12 md:grid-cols-2">
              {QUESTIONS.map(([question, answer]) => (
                <div key={question} className="border-t border-line py-4.5">
                  <h3 className="mb-1.5 font-serif text-title font-normal">{t(question)}</h3>
                  <p className="text-muted">{t(answer)}</p>
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
              <p id="footer-sections" className="microlabel mb-3 text-brass">
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
              <p className="microlabel mb-3 text-brass">{t('public.footer.account')}</p>
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
