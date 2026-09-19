'use client';

import * as Dialog from '@radix-ui/react-dialog';
import type { ComponentProps } from 'react';

import { cn } from '@/shared/utils/cn';

// The parts of shadcn/ui's Sheet (ui.shadcn.com/docs/components/sheet) the
// More sheet renders, written by hand with shadcn's names on the Radix Dialog
// we already ship (ADR 0004, design/system/navigation.md 3). Radix gives the
// dialog role, aria-modal, the focus trap, the page hidden from assistive
// technology, scroll lock and Escape returning focus to the trigger. Only the
// bottom side is built, and nothing animates, like Modal.

export const Sheet = Dialog.Root;
export const SheetTrigger = Dialog.Trigger;
export const SheetClose = Dialog.Close;

export function SheetTitle({ className, ...props }: ComponentProps<typeof Dialog.Title>) {
  return <Dialog.Title data-slot="sheet-title" className={cn('text-title', className)} {...props} />;
}

/**
 * A bottom sheet: the full width of a phone, centred at Modal's 560px from
 * 592px, over Modal's scrim. At most 85svh with its content scrolling
 * inside, and its bottom edge clear of the home indicator.
 */
export function SheetContent({ className, children, ...props }: ComponentProps<typeof Dialog.Content>) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay data-slot="sheet-overlay" className="fixed inset-0 z-40 bg-fg/60" />
      <Dialog.Content
        data-slot="sheet-content"
        // Radix hides the rest of the page but does not say the dialog is
        // modal; the visible title names it and there is no description.
        aria-modal="true"
        aria-describedby={undefined}
        className={cn(
          'fixed inset-x-0 bottom-0 z-50 flex max-h-[85svh] flex-col rounded-t-overlay border-t border-line bg-surface pb-[max(16px,env(safe-area-inset-bottom))] text-fg',
          'min-[37rem]:mx-auto min-[37rem]:max-w-[560px] min-[37rem]:border-x',
          className,
        )}
        {...props}
      >
        {children}
      </Dialog.Content>
    </Dialog.Portal>
  );
}
