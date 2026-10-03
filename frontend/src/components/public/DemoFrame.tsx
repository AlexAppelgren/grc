'use client';

import * as Dialog from '@radix-ui/react-dialog';
import Image from 'next/image';
import { type ReactNode, useState, useSyncExternalStore } from 'react';

import { buttonVariants } from '@/components/ui/Button';
import { DEMO_FRAME_NAME, isDemoFrame } from '@/features/demo/frame';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// The public page's demo (design/public/README.md "The demo"): the app itself
// in a frame, answered from recordings (features/demo). On a desktop it runs in
// place straight away (Alex, 2026-10-03). On a phone a frame inside a scrolling
// page would trap the thumb, so a picture of it, taken by the demo journey when
// it records, and one button open it full screen, over a page that stays still;
// nothing of the app loads before the press. A bar above it says it is a demo
// and can start it over.

const WIDE = '(min-width: 768px)';
const TRY = cn(buttonVariants({ variant: 'primary' }), 'h-12 px-6 text-title hover:bg-[color-mix(in_srgb,var(--color-button)_88%,var(--color-page))]');
const BAR_BUTTON = cn(buttonVariants({ variant: 'outline', size: 'small' }), 'h-11 hover:hover-fill');
const DESKTOP_HEIGHT = 'h-[min(760px,calc(100dvh-160px))]';

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

function Frame({ run, className }: { run: number; className: string }) {
  const t = useT();
  return <iframe key={run} name={DEMO_FRAME_NAME} src="/" title={t('public.demo.frameTitle')} className={cn('block w-full border-0 bg-page', className)} />;
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
          {/* Radix locks the page's scrolling from its overlay, so the page behind stays still. */}
          <Dialog.Overlay className="fixed inset-0 z-50 bg-page" />
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
        <a href="#case" className="sr-only focus:not-sr-only focus:mb-2 focus:inline-block focus:underline">
          {t('public.demo.skip')}
        </a>
        <div className="overflow-hidden rounded-card border border-line">
          <Bar onStartOver={startOver} />
          {/* Until the browser knows the width, the picture holds the frame's place. */}
          {layout === 'wide' ? (
            <Frame run={run} className={DESKTOP_HEIGHT} />
          ) : (
            <div className={cn('relative bg-subtle', DESKTOP_HEIGHT)}>
              <Poster form="desktop" />
            </div>
          )}
        </div>
      </div>
    </figure>
  );
}
