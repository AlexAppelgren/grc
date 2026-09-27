'use client';

import * as Dialog from '@radix-ui/react-dialog';
import Image from 'next/image';
import { type ReactNode, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import { buttonVariants } from '@/components/ui/Button';
import { DEMO_FRAME_NAME, isDemoFrame } from '@/features/demo/frame';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// The public page's demo (design/public/README.md "The demo"): the app itself
// in a frame, answered from recordings (features/demo). A visitor first sees a
// picture of it, taken by the demo journey when it records, and one button
// (Alex, 2026-09-27: proposal A). Nothing of the app loads until they press
// it: on a desktop the live app replaces the picture in place, on a phone it
// opens full screen, where a frame inside a scrolling page would trap the
// thumb. A bar above it says it is a demo and can start it over.

const WIDE = '(min-width: 768px)';
const TRY = cn(buttonVariants({ variant: 'primary' }), 'h-12 px-6 text-title hover:bg-[color-mix(in_srgb,var(--color-button)_88%,var(--color-page))]');
const BAR_BUTTON = cn(buttonVariants({ variant: 'outline', size: 'small' }), 'h-11 hover:hover-fill');

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(WIDE);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

// Inside the demo the page shows no second demo. The server cannot see the
// width, so the live frame waits for the browser; until then CSS picks the form.
function layoutNow(): 'nested' | 'wide' | 'narrow' {
  if (isDemoFrame()) return 'nested';
  return window.matchMedia(WIDE).matches ? 'wide' : 'narrow';
}

function PlayIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 14 14" fill="currentColor">
      <path d="M3 1.5v11l9-5.5z" />
    </svg>
  );
}

/**
 * The picture of the demo's Today in the reader's theme, filling its box. Served
 * as it is: the demo journey already writes it at the size it shows.
 */
function Poster({ form }: { form: 'desktop' | 'phone' }) {
  const t = useT();
  return (
    <>
      <Image src={`/demo/today-${form}-light.jpg`} alt={t('public.demo.picture')} fill unoptimized className="object-cover object-top dark:hidden" />
      <Image src={`/demo/today-${form}-dark.jpg`} alt={t('public.demo.picture')} fill unoptimized className="hidden object-cover object-top dark:block" />
    </>
  );
}

function Frame({ run, className, focus = false }: { run: number; className: string; focus?: boolean }) {
  const t = useT();
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    if (focus) frame.current?.focus();
  }, [focus]);
  return <iframe key={run} ref={frame} name={DEMO_FRAME_NAME} src="/" title={t('public.demo.frameTitle')} className={cn('block w-full border-0 bg-page', className)} />;
}

function Bar({ onStartOver, children }: { onStartOver: () => void; children?: ReactNode }) {
  const t = useT();
  return (
    <div className="flex items-center gap-2 border-b border-line bg-sand px-4 py-2">
      <span className="text-body font-semibold">{t('public.demo.label')}</span>
      <span className="text-body text-brass">{t('public.demo.bank')}</span>
      <button type="button" onClick={onStartOver} className={cn(BAR_BUTTON, 'ml-auto')}>
        {t('public.demo.startOver')}
      </button>
      {children}
    </div>
  );
}

export function DemoFrame() {
  const t = useT();
  const layout = useSyncExternalStore(subscribe, layoutNow, () => 'pending');
  const [live, setLive] = useState(false);
  const [run, setRun] = useState(0);
  const startOver = () => setRun((n) => n + 1);

  if (layout === 'nested') return null;
  return (
    <figure>
      <Dialog.Root>
        <div className="overflow-hidden rounded-card border border-line bg-subtle md:hidden">
          <div className="relative h-[260px]">
            <Poster form="phone" />
          </div>
          <div className="flex flex-col gap-3 border-t border-line p-4">
            <Dialog.Trigger className={cn(TRY, 'w-full')}>
              <PlayIcon />
              {t('public.demo.open')}
            </Dialog.Trigger>
            <p className="text-body">{t('public.demo.caption')}</p>
          </div>
        </div>
        <Dialog.Portal>
          <Dialog.Content
            aria-modal="true"
            aria-describedby={undefined}
            className="fixed inset-0 z-50 flex flex-col bg-page pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] text-fg"
          >
            <Dialog.Title className="sr-only">{t('public.demo.label')}</Dialog.Title>
            <Bar onStartOver={startOver}>
              <Dialog.Close className={BAR_BUTTON}>{t('public.demo.close')}</Dialog.Close>
            </Bar>
            <Frame run={run} className="min-h-0 flex-1" />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="hidden md:block">
        {live && layout === 'wide' ? (
          <>
            <a href="#case" className="sr-only focus:not-sr-only focus:mb-2 focus:inline-block focus:underline">
              {t('public.demo.skip')}
            </a>
            <div className="overflow-hidden rounded-card border border-line">
              <Bar onStartOver={startOver} />
              <Frame run={run} focus className="h-[min(760px,calc(100dvh-160px))]" />
            </div>
          </>
        ) : (
          <div className="relative h-[min(760px,calc(100dvh-120px))] overflow-hidden rounded-card border border-line bg-subtle">
            <Poster form="desktop" />
            {/* The button and its line sit on solid paper, so no text of the picture runs behind them. */}
            <div className="absolute inset-0 flex items-center justify-center bg-page/60 px-6">
              <div className="flex flex-col items-center gap-4 rounded-card border border-line bg-page px-8 py-6 text-center">
                <button type="button" onClick={() => setLive(true)} className={TRY}>
                  <PlayIcon />
                  {t('public.demo.open')}
                </button>
                <p className="max-w-[40ch] text-title font-normal">{t('public.demo.caption')}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </figure>
  );
}
