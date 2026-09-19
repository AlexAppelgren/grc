import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// Prototype `.notice`, `.notice.warn` and `.notice.bad`
// (design/screens/admin-footprint.html, states.html): a banner about the
// record in front of the person, never a toast. `bad` is the shape a refusal
// takes where the action was taken, so it is announced. Other attributes
// (a data- hook, an aria- label) pass through to the element.

export type NoticeTone = 'plain' | 'warn' | 'bad';

const border: Record<NoticeTone, string> = {
  plain: 'border-line bg-surface-2',
  warn: 'border-warning bg-warning-soft',
  bad: 'border-negative bg-negative-soft',
};

export function Notice({ tone = 'plain', children, className, ...rest }: { tone?: NoticeTone; children: ReactNode } & Omit<HTMLAttributes<HTMLDivElement>, 'role'>) {
  return (
    <div role={tone === 'bad' ? 'alert' : 'status'} data-notice={tone} className={cn('mb-4 rounded-m border p-4', border[tone], className)} {...rest}>
      {children}
    </div>
  );
}
