'use client';

import type { ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// Prototype `.chip` and the footprint card's `.chip.off`
// (design/screens/admin-footprint.html): a pressed chip is a term the
// footprint holds; a struck one is a term a pending request is about to
// switch off. A chip carries no tone, so it is not a pill.

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
        'min-h-9 rounded-full border px-3.5 py-1.5 text-meta font-semibold whitespace-nowrap disabled:cursor-default',
        pressed ? 'border-fg bg-surface-2 text-fg' : 'border-line bg-transparent text-muted',
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
