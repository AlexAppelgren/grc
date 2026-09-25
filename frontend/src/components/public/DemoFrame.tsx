'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { useSyncExternalStore } from 'react';

import { buttonVariants } from '@/components/ui/Button';
import { DEMO_FRAME_NAME, isDemoFrame } from '@/features/demo/frame';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// The public page's demo (design/public/README.md "The demo"): the app itself
// in a frame, answered from recordings (features/demo). The app is a large
// download, so nobody pays for it until they come near it. On a desktop the
// frame sits in the page and loads when it scrolls close. On a phone, where a
// frame inside a scrolling page traps the thumb, a button opens it full screen
// and nothing loads before that.

const WIDE = '(min-width: 768px)';

function Frame({ className }: { className: string }) {
  const t = useT();
  return <iframe name={DEMO_FRAME_NAME} src="/" title={t('public.demo.frameTitle')} loading="lazy" className={cn('block w-full border-0 bg-page', className)} />;
}

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(WIDE);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

// Inside the demo the page shows no second demo. The server cannot see the
// width, so the frame waits for the browser; until then CSS picks the form.
function layoutNow(): 'nested' | 'wide' | 'narrow' {
  if (isDemoFrame()) return 'nested';
  return window.matchMedia(WIDE).matches ? 'wide' : 'narrow';
}

export function DemoFrame() {
  const t = useT();
  const layout = useSyncExternalStore(subscribe, layoutNow, () => 'pending');

  if (layout === 'nested') return null;
  return (
    <figure>
      <Dialog.Root>
        <div className="rounded-card border border-line bg-subtle p-4 md:hidden">
          <p className="max-w-[46ch] text-title font-normal">{t('public.demo.caption')}</p>
          <Dialog.Trigger className={cn(buttonVariants({ variant: 'outline' }), 'mt-4 hover:hover-fill')}>{t('public.demo.open')}</Dialog.Trigger>
        </div>
        <Dialog.Portal>
          <Dialog.Content
            aria-modal="true"
            aria-describedby={undefined}
            className="fixed inset-0 z-50 flex flex-col bg-page pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] text-fg"
          >
            <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2">
              <Dialog.Title className="text-meta text-muted">{t('public.demo.label')}</Dialog.Title>
              <Dialog.Close className={cn(buttonVariants({ variant: 'outline', size: 'small' }), 'hover:hover-fill')}>{t('public.demo.close')}</Dialog.Close>
            </div>
            <Frame className="min-h-0 flex-1" />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div className="hidden h-[min(760px,calc(100dvh-120px))] overflow-hidden rounded-card border border-line bg-subtle md:block">{layout === 'wide' ? <Frame className="h-full" /> : null}</div>
      <figcaption className="mt-3 hidden text-meta text-muted md:block">{t('public.demo.caption')}</figcaption>
    </figure>
  );
}
