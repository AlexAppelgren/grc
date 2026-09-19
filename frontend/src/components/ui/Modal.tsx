'use client';

import * as Dialog from '@radix-ui/react-dialog';
import type { ReactNode } from 'react';

// Prototype `.modal` and `.box` on Radix Dialog (focus trap, escape, labels).
// The title is the dialog's accessible name; the body is its description.

export function Modal({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: ReactNode }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-fg/60" />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 z-50 max-h-[86vh] w-[calc(100%-32px)] max-w-[560px] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-overlay border border-line bg-surface p-5 text-fg"
          aria-describedby={description === undefined ? undefined : 'modal-description'}
        >
          <Dialog.Title className="mb-3 text-title">{title}</Dialog.Title>
          {description !== undefined ? (
            <Dialog.Description id="modal-description" className="mb-3 text-muted">
              {description}
            </Dialog.Description>
          ) : null}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
