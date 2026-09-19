import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// Prototype `.panel` and `.panel.sand`, and `.rows`/`.row` for lists.

export function Panel({ title, sand = false, className, children, ...rest }: { title?: string; sand?: boolean; children: ReactNode } & HTMLAttributes<HTMLElement>) {
  return (
    <section className={cn('mb-4 rounded-m border p-5', sand ? 'border-sand-2 bg-sand' : 'border-line bg-surface', className)} {...rest}>
      {title !== undefined ? <h2 className="mb-3">{title}</h2> : null}
      {children}
    </section>
  );
}

export function Rows({ children, className, ...rest }: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('grid gap-2.5', className)} {...rest}>
      {children}
    </div>
  );
}

export function Row({ children, className, ...rest }: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('rounded-m border border-line bg-surface px-4.5 py-4', className)} {...rest}>
      {children}
    </div>
  );
}

/** Prototype `.meta`: the muted facts line under a row title. */
export function Meta({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-muted', className)}>{children}</div>;
}
