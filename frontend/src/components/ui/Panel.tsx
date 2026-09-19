import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// foundations.md "Card" (shadcn's Card, one radius step tighter): the
// surface, a 1px hairline, 8px radius, 16px padding, no shadow and no sand
// fill. `.rows`/`.row` for lists: 8px apart, 12px by 16px.

export function Panel({ title, className, children, ...rest }: { title?: string; children: ReactNode } & HTMLAttributes<HTMLElement>) {
  return (
    <section className={cn('mb-4 rounded-card border border-line bg-surface p-4', className)} {...rest}>
      {title !== undefined ? <h2 className="mb-3">{title}</h2> : null}
      {children}
    </section>
  );
}

export function Rows({ children, className, ...rest }: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('grid gap-2', className)} {...rest}>
      {children}
    </div>
  );
}

export function Row({ children, className, ...rest }: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('rounded-card border border-line bg-surface px-4 py-3', className)} {...rest}>
      {children}
    </div>
  );
}

/** Prototype `.meta`: the muted facts line under a row title. */
export function Meta({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('flex flex-wrap items-center gap-x-2 gap-y-1.5 text-meta text-muted', className)}>{children}</div>;
}
