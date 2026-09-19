'use client';

import type { ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// Prototype `.chip` and the footprint card's `.chip.off`
// (design/screens/admin-footprint.html): a pressed chip is a term the
// footprint holds; a struck one is a term a pending request is about to
// switch off. A chip carries no tone, so it is not a pill. foundations.md
// "Toggle": 32px, 12px sides, 6px radius, `body` at 500, so it never reads
// as a pill.

export function Chip({
  pressed,
  struck = false,
  disabled = false,
  onClick,
  children,
}: {
  pressed: boolean;
  /** The term is still held but a waiting request would remove it. */
  struck?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      data-struck={struck ? '' : undefined}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'inline-flex h-8 items-center rounded-control border px-3 text-body font-medium whitespace-nowrap disabled:cursor-default',
        pressed ? 'border-line-strong bg-neutral-soft text-fg' : 'border-line-control bg-surface text-muted enabled:hover:text-fg',
        struck && 'line-through opacity-55',
      )}
    >
      {children}
    </button>
  );
}

/** Prototype `.filters`: a row of chips. */
export function ChipRow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('flex flex-wrap items-center gap-2', className)}>{children}</div>;
}
