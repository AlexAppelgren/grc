import { Fragment, type ReactNode } from 'react';

import { DemoFrame } from '@/components/public/DemoFrame';
import { InkHead } from '@/components/public/InkHead';
import { RevisedEntry } from '@/components/public/RevisedEntry';
import { supportContact } from '@/shared/brand';
import { createT, defaultLocale, localeTags, type MessageKey } from '@/shared/i18n';
import { SIGN_IN } from '@/shared/navigation/registry';
import { cn } from '@/shared/utils/cn';

// The public page (design/public/index.html, the Lexicon direction, Alex
// 2026-11-11). The brand name is a pronunciation, so the page is a dictionary:
// the phonetic logo cut out of a green page with ink moving behind it, then one
// entry per idea, each with its headword, its part of speech and numbered
// senses. Two entries are struck out by hand and corrected in pen, the redline
// the product keeps. The page has one appearance in either theme, and the
// demo inside it shows the dark recordings. Nothing on it is italic, and
// everything a visitor reads runs in the text colour; grey is left to short
// labels (Alex, 2026-09-25). Colours are the public set in brand.css.

const t = createT(defaultLocale);
const LIST = new Intl.ListFormat(localeTags[defaultLocale], { type: 'unit', style: 'short' });

// A jump lands below the sticky bar, which is 64 px tall.
const ANCHOR = 'scroll-mt-20';

// The two actions share one row on a phone, with the main action on the right.
const ACTS = 'flex flex-wrap gap-3 max-[700px]:flex-nowrap max-[700px]:justify-end max-[700px]:gap-2';
const BUTTON =
  'inline-flex h-[3.1rem] items-center gap-2.5 rounded-xs border border-public-paper px-6 font-sans text-title whitespace-nowrap hover:border-public-brass hover:bg-public-brass hover:text-public-deep max-[700px]:px-4 max-[409px]:h-11 max-[409px]:px-3 max-[409px]:text-body max-[359px]:px-2.5';
const SOLID = 'bg-public-paper text-brand max-[700px]:order-2';
// The bar's buttons are a step smaller than the page's.
const BAR = 'h-10 px-[1.1rem] max-[700px]:px-3.5 max-[409px]:h-10';
const NUMBER = 'font-serif-display text-display font-normal text-public-brass';
const TERM = 'block font-serif-display text-display font-normal';
const LINK = 'underline decoration-1 underline-offset-[0.25em] hover:text-public-brass';

// The redline, drawn when its entry comes into view (RevisedEntry). Under
// reduced motion none of these apply, so the finished state shows.
const STRIKE = 'motion-safe:group-data-[reveal=waiting]/entry:[clip-path:inset(-50%_100%_-50%_0)] motion-safe:group-data-[reveal=seen]/entry:animate-strike';
const WRITE = 'motion-safe:group-data-[reveal=waiting]/entry:[clip-path:inset(-50%_100%_-50%_0)] motion-safe:group-data-[reveal=seen]/entry:animate-write';
const INK = 'motion-safe:group-data-[reveal=waiting]/entry:opacity-0 motion-safe:group-data-[reveal=seen]/entry:animate-ink';

const NAV: readonly (readonly [string, MessageKey])[] = [
  ['demo', 'public.nav.demo'],
  ['watch', 'public.nav.method'],
  ['source', 'public.nav.sources'],
];

const HEADWORDS = {
  watch: 'public.entry.watch.headword',
  inventory: 'public.entry.inventory.headword',
  ask: 'public.entry.ask.headword',
  evidence: 'public.entry.evidence.headword',
  signoff: 'public.entry.signOff.headword',
  source: 'public.entry.source.headword',
} as const satisfies Record<string, MessageKey>;

const STEPS: readonly (readonly [MessageKey, MessageKey])[] = [
  ['public.entry.signOff.sighted.name', 'public.entry.signOff.sighted.body'],
  ['public.entry.signOff.proposed.name', 'public.entry.signOff.proposed.body'],
  ['public.entry.signOff.confirmed.name', 'public.entry.signOff.confirmed.body'],
  ['public.entry.signOff.applied.name', 'public.entry.signOff.applied.body'],
  ['public.entry.signOff.assessed.name', 'public.entry.signOff.assessed.body'],
  ['public.entry.signOff.signedOff.name', 'public.entry.signOff.signedOff.body'],
];

const COVERAGE: readonly (readonly [MessageKey, MessageKey, MessageKey])[] = [
  ['public.coverage.se.name', 'public.coverage.se.sources', 'public.coverage.se.languages'],
  ['public.coverage.dk.name', 'public.coverage.dk.sources', 'public.coverage.dk.languages'],
  ['public.coverage.no.name', 'public.coverage.no.sources', 'public.coverage.no.languages'],
  ['public.coverage.fi.name', 'public.coverage.fi.sources', 'public.coverage.fi.languages'],
  ['public.coverage.eu.name', 'public.coverage.eu.sources', 'public.coverage.eu.languages'],
];

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

function PlayIcon() {
  return (
    // Below 360 px the two actions only fit in one row without it.
    <svg aria-hidden="true" viewBox="0 0 14 14" fill="currentColor" className="size-3.5 shrink-0 max-[359px]:hidden">
      <path d="M3 1.5v11l9-5.5z" />
    </svg>
  );
}

/**
 * One dictionary entry: the headword on the left, sticky on a wide screen, and
 * the senses on the right; `wide` spans both columns under them. The sticky
 * headword is held inside its own row, so it never rides over the wide row.
 */
function Entry({
  id,
  headword,
  label,
  revised = false,
  children,
  wide,
}: {
  id: string;
  headword: ReactNode;
  label: string;
  revised?: boolean;
  children: ReactNode;
  wide?: ReactNode;
}) {
  const titleId = `${id}-title`;
  const classes = cn(ANCHOR, 'group/entry px-(--gutter) pt-[clamp(3.5rem,8vw,7.5rem)]');
  const body = (
    <>
      <div className="grid items-start gap-6 min-[860px]:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] min-[860px]:gap-[clamp(1.5rem,5vw,5rem)]">
        <div className="min-[860px]:sticky min-[860px]:top-22">
          <h2 id={titleId} className="font-serif-display text-headword">
            {headword}
          </h2>
          <p className="mt-[1.1rem] font-sans text-title font-medium text-public-brass">{label}</p>
        </div>
        <div className="min-w-0">{children}</div>
      </div>
      {wide === undefined ? null : <div className="mt-6 min-w-0 min-[860px]:mt-[clamp(1.5rem,5vw,5rem)]">{wide}</div>}
    </>
  );
  return revised ? (
    <RevisedEntry id={id} labelledBy={titleId} className={classes}>
      {body}
    </RevisedEntry>
  ) : (
    <section id={id} aria-labelledby={titleId} className={classes}>
      {body}
    </section>
  );
}

/** Numbered senses; a single sense carries no number. */
function Senses({ items }: { items: readonly ReactNode[] }) {
  if (items.length === 1) return <p className="mb-6 max-w-[38rem]">{items[0]}</p>;
  return (
    <ol>
      {items.map((item, index) => (
        <li key={index} className="mb-[1.6rem] grid max-w-[38rem] grid-cols-[2.6rem_minmax(0,1fr)] items-baseline">
          <span className={NUMBER}>{index + 1}</span>
          <div>{item}</div>
        </li>
      ))}
    </ol>
  );
}

/** A usage line under a sense. */
function Usage({ children }: { children: ReactNode }) {
  return <span className="mt-2.5 block border-l-2 border-public-brass pl-3.5 font-sans text-title font-normal">{children}</span>;
}

/** A struck claim and its correction in pen, inside a sense. */
function Corrected({ text, struck, pen, later = false }: { text: MessageKey; struck: MessageKey; pen: MessageKey; later?: boolean }) {
  return (
    <>
      {t(text)} <del className="text-public-struck decoration-public-pen decoration-[length:0.09em]">{t(struck)}</del>{' '}
      <ins className={cn('font-hand text-pen tracking-normal no-underline', INK, later && '[animation-delay:1.5s]')}>{t(pen)}</ins>
    </>
  );
}

/** A struck headword, drawn through by hand, and the entry it now points to. */
function StruckHeadword({ word, correction, path }: { word: MessageKey; correction: MessageKey; path: string }) {
  return (
    <>
      <del className="relative inline-block whitespace-nowrap text-public-struck no-underline">
        {t(word)}
        <svg viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true" className={cn('pointer-events-none absolute top-[12%] -left-[3%] h-[80%] w-[106%] overflow-visible', STRIKE)}>
          <path d={path} className="fill-none stroke-public-pen stroke-6 [stroke-linecap:round] [vector-effect:non-scaling-stroke]" />
        </svg>
      </del>
      <ins className={cn('mt-[0.28em] ml-[0.08em] block origin-left -rotate-2 font-hand text-pen-head tracking-normal no-underline', WRITE)}>
        <svg aria-hidden="true" viewBox="0 0 10 10" className="mr-[0.16em] inline-block size-[0.4em] align-baseline">
          <path d="M1 8 5 3l4 5" fill="none" stroke="currentColor" strokeWidth={1.5} />
        </svg>
        {t(correction)}
      </ins>
    </>
  );
}

/** "See also watch, source." with each headword a link to its entry. */
function CrossRefs({ also = false, refs }: { also?: boolean; refs: readonly (keyof typeof HEADWORDS)[] }) {
  const slot = '\u0001';
  const [before = '', after = ''] = t(also ? 'public.seeAlso' : 'public.see', { refs: slot }).split(slot);
  return (
    <p className="mt-8 max-w-[38rem]">
      {before}
      {LIST.formatToParts(refs).map((part, index) =>
        part.type === 'element' ? (
          <a key={index} href={`#${part.value}`} className={LINK}>
            {t(HEADWORDS[part.value as keyof typeof HEADWORDS])}
          </a>
        ) : (
          <Fragment key={index}>{part.value}</Fragment>
        ),
      )}
      {after}
    </p>
  );
}

export function PublicPage() {
  const writeTo =
    supportContact === '' ? null : `mailto:${supportContact}?subject=${encodeURIComponent(t('public.request.mailSubject'))}`;
  const noun = t('public.label.noun');
  const verb = t('public.label.verb');
  return (
    // `dark` keeps the demo's own tokens and pictures dark on the green page.
    // The gutter is where the logo's brackets start and end (Alex, 2026-11-11), so the bar, the
    // entries and the demo line up with them. The logo keeps the reference's size: its frame sat
    // 0.55 of the reference margin (--margin) in from each side, and the brackets span 87.72 % of
    // that frame (InkHead.tsx). Percentages resolve against the page's width.
    <div
      data-public-page=""
      className="dark relative min-h-dvh bg-brand font-serif text-sense text-public-paper [--margin:clamp(1.25rem,5vw,5.5rem)] [--gutter:max(calc((100%_-_0.8772*(100%_-_1.1*var(--margin)))/2),env(safe-area-inset-left),env(safe-area-inset-right))]"
    >
      {/* The paper's grain, over the whole page and its bar, as in the reference; the demo's dialog sits above it. */}
      <div aria-hidden="true" className="grain pointer-events-none fixed inset-0 z-30 opacity-[0.22] mix-blend-overlay" />
      <a
        href="#top"
        className="sr-only focus:not-sr-only focus:absolute focus:top-[max(8px,env(safe-area-inset-top))] focus:left-[max(8px,env(safe-area-inset-left))] focus:z-50 focus:bg-public-paper focus:px-4 focus:py-2 focus:font-sans focus:text-brand"
      >
        {t('shell.skipToContent')}
      </a>

      {/* Sign in is a plain link, never next/link: a page load reaches the server, which
          moves it to the app's own host when there is one (src/proxy.ts). */}
      <header className="sticky top-[env(safe-area-inset-top,0px)] z-20 flex h-16 items-center gap-8 bg-brand px-(--gutter) font-sans text-title font-normal">
        <span className="hidden text-public-dim min-[860px]:inline">{t('public.topLine')}</span>
        <nav aria-label={t('public.nav.label')} className="ml-auto hidden items-center gap-7 min-[860px]:flex">
          {NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="hover:underline hover:underline-offset-[0.3em]">
              {t(label)}
            </a>
          ))}
        </nav>
        {/* Sign in is the main action, filled and on the right (Alex, 2026-11-11). */}
        <div className="ml-auto flex items-center gap-3 max-[700px]:gap-2 min-[860px]:ml-0">
          <a href="#request" className={cn(BUTTON, BAR)}>
            {t('public.action.requestAccess')}
          </a>
          <a href={SIGN_IN} className={cn(BUTTON, SOLID, BAR)}>
            {t('public.action.signIn')}
          </a>
        </div>
      </header>

      <main id="top" className={ANCHOR}>
        <InkHead phonetic={t('public.phonetic')} />

        {/* The page's own entry (Alex, 2026-11-11): the ink logo above shows its name, so the h1 is for
            screen readers and search engines; the deck and its actions take the wide column on the
            left, and where the name comes from sits on the right, level with the deck. */}
        <section
          id="bleqq"
          aria-labelledby="bleqq-title"
          className="grid items-baseline gap-6 px-(--gutter) pt-[clamp(2rem,4vw,3.5rem)] min-[860px]:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] min-[860px]:gap-[clamp(1.5rem,5vw,5rem)]"
        >
          <h1 id="bleqq-title" className="sr-only">
            {t('public.entry.bleqq.headword')}
          </h1>
          <p className="font-sans text-title font-medium text-public-brass min-[860px]:order-2 min-[860px]:text-right">{t('public.entry.bleqq.origin')}</p>
          <div className="min-w-0">
            <p className="max-w-[24em] font-serif-display text-lede">{t('public.entry.bleqq.deck')}</p>
            <div className={cn(ACTS, 'mt-8')}>
              <a href="#demo" className={cn(BUTTON, SOLID)}>
                <PlayIcon />
                {t('public.demo.open')}
              </a>
              <a href="#request" className={BUTTON}>
                {t('public.action.requestAccess')}
              </a>
            </div>
            <CrossRefs also refs={['watch', 'inventory', 'ask', 'evidence']} />
          </div>
        </section>

        <Entry
          id="demo"
          headword={t('public.entry.demo.headword')}
          label={noun}
          wide={
            <div className="mt-[clamp(0.5rem,2vw,1.5rem)] font-sans">
              <DemoFrame />
            </div>
          }
        >
          <Senses items={[t('public.entry.demo.sense1'), t('public.entry.demo.sense2')]} />
        </Entry>

        {/* The case against the two tools a bank uses today; the demo's skip link lands here. */}
        <div id="case" className={ANCHOR}>
          <Entry
            id="spreadsheet"
            revised
            headword={<StruckHeadword word="public.entry.spreadsheet.headword" correction="public.entry.spreadsheet.correction" path="M0 11 C 18 7, 34 14, 55 9 S 88 8, 100 11" />}
            label={t('public.label.nounObsolete')}
          >
            <Senses
              items={[
                <Corrected key="1" text="public.entry.spreadsheet.sense1" struck="public.entry.spreadsheet.sense1Struck" pen="public.entry.spreadsheet.sense1Pen" />,
                <Corrected key="2" later text="public.entry.spreadsheet.sense2" struck="public.entry.spreadsheet.sense2Struck" pen="public.entry.spreadsheet.sense2Pen" />,
              ]}
            />
            <CrossRefs refs={['inventory', 'evidence']} />
          </Entry>

          <Entry
            id="inbox"
            revised
            headword={<StruckHeadword word="public.entry.inbox.headword" correction="public.entry.inbox.correction" path="M0 9 C 22 13, 41 6, 63 11 S 90 12, 100 8" />}
            label={t('public.label.nounObsolete')}
          >
            <Senses items={[<Corrected key="1" text="public.entry.inbox.sense1" struck="public.entry.inbox.sense1Struck" pen="public.entry.inbox.sense1Pen" />]} />
            <CrossRefs refs={['watch', 'source']} />
          </Entry>
        </div>

        <Entry id="watch" headword={t('public.entry.watch.headword')} label={verb}>
          <Senses
            items={[
              t('public.entry.watch.sense1'),
              <>
                {t('public.entry.watch.sense2')}
                <Usage>{t('public.entry.watch.usage')}</Usage>
              </>,
            ]}
          />
          <CrossRefs also refs={['source', 'signoff']} />
        </Entry>

        <Entry id="inventory" headword={t('public.entry.inventory.headword')} label={noun}>
          <Senses items={[t('public.entry.inventory.sense1'), t('public.entry.inventory.sense2')]} />
          <figure className="mt-7 max-w-[35.4rem] -rotate-[0.6deg] bg-public-paper p-[clamp(1.25rem,2.4vw,2rem)] text-brand min-[860px]:ml-[2.6rem]">
            <figcaption className="mb-3.5 flex flex-wrap justify-between gap-x-4 font-sans text-body">
              <span>{t('public.entry.inventory.sheetTitle')}</span>
              <span>{t('public.entry.inventory.sheetVersion')}</span>
            </figcaption>
            <p className="text-sheet">
              {t('public.entry.inventory.sheetText1')} <del className="text-public-del">{t('public.entry.inventory.sheetDel1')}</del>{' '}
              <ins className="bg-public-ins px-[0.08em] no-underline shadow-[0_0.12em_0_var(--bleqq-public-ins-line)]">{t('public.entry.inventory.sheetIns1')}</ins>{' '}
              {t('public.entry.inventory.sheetText2')} <del className="text-public-del">{t('public.entry.inventory.sheetDel2')}</del>{' '}
              <ins className="bg-public-ins px-[0.08em] no-underline shadow-[0_0.12em_0_var(--bleqq-public-ins-line)]">{t('public.entry.inventory.sheetIns2')}</ins>
            </p>
          </figure>
        </Entry>

        <Entry id="ask" headword={t('public.entry.ask.headword')} label={verb}>
          <Senses items={[t('public.entry.ask.sense1'), t('public.entry.ask.sense2')]} />
        </Entry>

        <Entry id="evidence" headword={t('public.entry.evidence.headword')} label={noun}>
          <Senses
            items={[
              t('public.entry.evidence.sense1'),
              <>
                {t('public.entry.evidence.sense2')}
                <Usage>{t('public.entry.evidence.usage')}</Usage>
              </>,
            ]}
          />
        </Entry>

        <Entry id="library" headword={t('public.entry.library.headword')} label={noun}>
          <Senses items={[t('public.zones.library.body')]} />
        </Entry>

        <Entry id="zone" headword={t('public.entry.zone.headword')} label={noun}>
          <Senses items={[t('public.zones.yours.body'), t('public.zones.footnote')]} />
        </Entry>

        <Entry id="signoff" headword={t('public.entry.signOff.headword')} label={verb}>
          <Senses items={[t('public.entry.signOff.sense1')]} />
          <ol className="max-w-[38rem]">
            {STEPS.map(([name, body], index) => (
              <li key={name} className="grid grid-cols-[2.2rem_minmax(0,1fr)] items-baseline py-[0.55rem] min-[860px]:grid-cols-[2.6rem_9.5rem_minmax(0,1fr)]">
                <span className={NUMBER}>{index + 1}</span>
                <b className="font-serif-display text-display font-normal">{t(name)}</b>
                <span className="col-start-2 min-[860px]:col-start-auto">{t(body)}</span>
              </li>
            ))}
          </ol>
        </Entry>

        <Entry id="source" headword={t('public.entry.source.headword')} label={noun}>
          <Senses items={[t('public.entry.source.sense1')]} />
          <table className="w-full max-w-[44rem] border-collapse">
            <caption className="sr-only">{t('public.coverage.title')}</caption>
            <tbody>
              {COVERAGE.map(([name, sources, languages]) => (
                <tr key={name} className="block py-3 min-[860px]:table-row min-[860px]:py-0">
                  <th
                    scope="row"
                    className="block text-left align-baseline font-serif-display text-display font-normal whitespace-nowrap min-[860px]:table-cell min-[860px]:w-[1%] min-[860px]:py-[0.7rem] min-[860px]:pr-6"
                  >
                    {t(name)}
                  </th>
                  <td className="block py-0.5 align-baseline min-[860px]:table-cell min-[860px]:py-[0.7rem]">
                    {t(sources)}
                    <small className="block font-sans text-body text-public-dim">{t(languages)}</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Entry>

        <Entry id="assurance" headword={t('public.entry.assurance.headword')} label={noun}>
          <p className="mb-6 max-w-[38rem]">{t('public.assurance.title')}</p>
          <Senses
            items={ASSURANCE.map(([term, body]) => (
              <Fragment key={term}>
                <b className={TERM}>{t(term)}</b>
                {t(body)}
              </Fragment>
            ))}
          />
        </Entry>

        <Entry id="question" headword={t('public.entry.question.headword')} label={noun}>
          <Senses
            items={QUESTIONS.map(([question, answer]) => (
              <Fragment key={question}>
                <b className={TERM}>{t(question)}</b>
                {t(answer)}
              </Fragment>
            ))}
          />
        </Entry>

        <section id="request" aria-labelledby="request-title" className={cn(ANCHOR, 'mt-[clamp(3.5rem,8vw,7.5rem)] bg-public-deep px-(--gutter) pt-[clamp(4rem,10vw,9rem)]')}>
          <h2 id="request-title" className="mb-8 font-serif-display text-headword">
            {t('public.request.title')}
          </h2>
          {writeTo === null ? <p className="mb-8 max-w-[38rem]">{t('public.request.invited')}</p> : null}
          <div className={ACTS}>
            <a href={SIGN_IN} className={cn(BUTTON, SOLID)}>
              {t('public.action.signIn')}
            </a>
            {writeTo === null ? null : (
              <a href={writeTo} className={BUTTON}>
                {t('public.action.requestAccess')}
              </a>
            )}
          </div>
        </section>
      </main>

      <footer className="flex flex-wrap gap-x-8 gap-y-2 bg-public-deep px-(--gutter) pt-[clamp(3rem,7vw,6rem)] pb-[max(2.5rem,env(safe-area-inset-bottom))] font-sans text-body text-public-dim">
        <span className="font-mono text-public-paper">{t('public.phonetic')}</span>
        <span>{t('public.footer.pronounced')}</span>
        <span className="ml-auto">{t('public.footer.copyright', { year: String(new Date().getFullYear()) })}</span>
      </footer>
    </div>
  );
}
